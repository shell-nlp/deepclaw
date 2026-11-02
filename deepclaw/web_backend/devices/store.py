"""共享数据库设备队列与连接租约，支持多服务实例。"""

import asyncio
import hashlib
import secrets
import time
import uuid
from pathlib import Path

from sqlmodel import SQLModel, select, update
from sqlalchemy.exc import IntegrityError

from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.db import resolve_metadata_db_url
from deepclaw.web_backend.devices.models import Device, DevicePairing, DeviceTask
from deepclaw.web_backend.devices.schemas import DevicePolicyRequest, DeviceEventRequest

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "rejected", "uncertain"})
CAPABILITIES = {"list_files": "files.read", "read_file": "files.read", "write_file": "files.write", "run_command": "command.run"}
ONLINE_SECONDS = 30


def digest(value: str) -> str:
    """计算凭据散列，原始凭据不落服务端数据库。

    Args:
        value: 原始凭据。
    """
    return hashlib.sha256(value.encode()).hexdigest()


class DeviceStore:
    """设备与任务的 SQLModel 异步存储。"""

    def __init__(self, db_url: str | None = None):
        """初始化连接，实际建表延迟到首次访问。

        Args:
            db_url: 测试或部署使用的数据库地址。
        """
        self.engine = create_async_engine_from_url(db_url or resolve_metadata_db_url("devices.db"))
        self.sessions = build_async_sessionmaker(self.engine)
        self._ready = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        """仅创建设备模块的三张表。

        Args:
            无。
        """
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                async with self.engine.begin() as connection:
                    await connection.run_sync(SQLModel.metadata.create_all, tables=[Device.__table__, DevicePairing.__table__, DeviceTask.__table__])
                self._ready = True

    async def pair(self, user_id: str):
        """生成五分钟有效的一次性配对码。

        Args:
            user_id: 已登录的用户标识。
        """
        await self.initialize()
        code = secrets.token_urlsafe(24)
        expires = time.time() + 300
        async with self.sessions() as session:
            session.add(DevicePairing(code_hash=digest(code), owner_user_id=user_id, expires_at=expires))
            await session.commit()
        return code, expires

    async def claim(self, code: str, name: str, platform: str):
        """原子消费配对码并建立默认关闭的设备。

        Args:
            code: 一次性配对码。
            name: 用户设备名称。
            platform: 客户端操作系统。
        """
        await self.initialize()
        async with self.sessions() as session:
            pairing = await session.get(DevicePairing, digest(code))
            if pairing is None:
                raise ValueError("配对码无效或已过期")
            result = await session.exec(update(DevicePairing).where(
                DevicePairing.code_hash == pairing.code_hash, DevicePairing.used == False,  # noqa: E712
                DevicePairing.expires_at > time.time(),
            ).values(used=True))
            if not result.rowcount:
                raise ValueError("配对码无效或已过期")
            token = "dd_" + secrets.token_urlsafe(32)
            device = Device(id=uuid.uuid4().hex, owner_user_id=pairing.owner_user_id, name=name,
                            platform=platform, token_hash=digest(token))
            session.add(device)
            await session.commit()
            return device.id, token

    async def authenticate(self, token: str):
        """校验可撤销的设备专用凭据。

        Args:
            token: 客户端凭据。
        """
        await self.initialize()
        async with self.sessions() as session:
            return (await session.exec(select(Device).where(Device.token_hash == digest(token), Device.revoked == False))).first()  # noqa: E712

    async def device(self, device_id: str, user_id: str | None = None):
        """查询设备，并可附加用户归属校验。

        Args:
            device_id: 设备标识。
            user_id: 当前用户，空值仅供已鉴权连接使用。
        """
        await self.initialize()
        async with self.sessions() as session:
            device = await session.get(Device, device_id)
            if device is None or device.revoked or (user_id is not None and device.owner_user_id != user_id):
                return None
            return device

    async def devices(self, user_id: str):
        """列出当前用户的未解绑设备。

        Args:
            user_id: 已认证用户标识。
        """
        await self.initialize()
        async with self.sessions() as session:
            return list((await session.exec(select(Device).where(Device.owner_user_id == user_id, Device.revoked == False).order_by(Device.created_at))).all())  # noqa: E712

    async def revoke(self, device_id: str, user_id: str):
        """撤销设备凭据并取消未完成任务。

        Args:
            device_id: 设备标识。
            user_id: 当前用户。
        """
        async with self.sessions() as session:
            await session.exec(update(Device).where(Device.id == device_id, Device.owner_user_id == user_id).values(revoked=True, enabled=False))
            await session.exec(update(DeviceTask).where(DeviceTask.device_id == device_id, DeviceTask.status.not_in(TERMINAL)).values(cancel_requested=True))
            await session.commit()

    async def connect(self, device_id: str, connection_id: str) -> bool:
        """原子领取连接租约，拒绝同设备跨实例同时连接。

        Args:
            device_id: 已鉴权设备。
            connection_id: 本次随机连接标识。
        """
        async with self.sessions() as session:
            result = await session.exec(update(Device).where(
                Device.id == device_id, Device.revoked == False,  # noqa: E712
                (Device.connection_id == None) | (Device.last_seen < time.time() - ONLINE_SECONDS),  # noqa: E711
            ).values(connection_id=connection_id, enabled=False, last_seen=time.time()))
            await session.commit()
            return bool(result.rowcount)

    async def heartbeat(self, device_id: str, connection_id: str) -> bool:
        """续租，仅当前连接可更新在线时间。

        Args:
            device_id: 设备标识。
            connection_id: 当前连接租约。
        """
        async with self.sessions() as session:
            result = await session.exec(update(Device).where(Device.id == device_id, Device.connection_id == connection_id, Device.revoked == False).values(last_seen=time.time()))  # noqa: E712
            await session.commit()
            return bool(result.rowcount)

    async def disconnect(self, device_id: str, connection_id: str):
        """只释放当前连接，旧连接不能覆盖新连接状态。

        Args:
            device_id: 设备标识。
            connection_id: 当前连接租约。
        """
        async with self.sessions() as session:
            await session.exec(update(Device).where(Device.id == device_id, Device.connection_id == connection_id).values(connection_id=None, enabled=False))
            await session.commit()

    async def policy(self, device_id: str, connection_id: str, policy: DevicePolicyRequest):
        """更新客户端授权，失效旧版本的待执行与审批任务。

        Args:
            device_id: 设备标识。
            connection_id: 当前连接租约。
            policy: 客户端授权及单调版本。
        """
        async with self.sessions() as session:
            result = await session.exec(update(Device).where(
                Device.id == device_id, Device.connection_id == connection_id,
                Device.revoked == False, Device.revision < policy.revision,  # noqa: E712
            ).values(enabled=policy.enabled, revision=policy.revision,
                     capabilities=list(set(policy.capabilities)), roots=policy.roots, last_seen=time.time()))
            if not result.rowcount:
                raise ValueError("授权版本已失效，请重新连接")
            await session.exec(update(DeviceTask).where(DeviceTask.device_id == device_id,
                DeviceTask.status.not_in(TERMINAL), DeviceTask.revision != policy.revision).values(cancel_requested=True))
            await session.commit()

    async def create_task(self, *, device_id: str, user_id: str, operation: str, arguments: dict,
                          thread_id: str, tool_call_id: str):
        """校验归属与即时权限，使用工具调用 ID 稳定创建任务。

        Args:
            device_id: 目标设备。
            user_id: 可信运行用户。
            operation: 规范化操作。
            arguments: 已验证的操作参数。
            thread_id: 当前会话。
            tool_call_id: 当前工具调用标识。
        """
        await self.initialize()
        key = digest(f"{user_id}:{device_id}:{thread_id}:{tool_call_id}")
        async with self.sessions() as session:
            existing = await session.get(DeviceTask, key)
            if existing is not None:
                return existing
            device = await session.get(Device, device_id)
            if device is None or device.revoked or device.owner_user_id != user_id:
                raise ValueError("设备不可用")
            if not device.enabled or device.last_seen < time.time() - ONLINE_SECONDS or not device.connection_id:
                raise ValueError("设备离线或本机访问已关闭")
            if CAPABILITIES.get(operation) not in device.capabilities:
                raise ValueError("本机未授权此操作")
            task = DeviceTask(id=key, device_id=device_id, owner_user_id=user_id, operation=operation,
                              arguments=arguments, revision=device.revision, thread_id=thread_id,
                              tool_call_id=tool_call_id, expires_at=time.time() + 600)
            session.add(task)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return (await session.exec(select(DeviceTask).where(DeviceTask.id == key))).one()
            return task

    async def tasks(self, device_id: str, active: bool = False):
        """读取任务列表，连接只读取未结束任务。

        Args:
            device_id: 已校验归属的设备。
            active: 是否仅返回未结束任务。
        """
        async with self.sessions() as session:
            statement = select(DeviceTask).where(DeviceTask.device_id == device_id)
            if active:
                statement = statement.where(DeviceTask.status.not_in(TERMINAL))
            statement = statement.order_by(DeviceTask.created_at.desc())
            return list((await session.exec(statement if active else statement.limit(50))).all())

    async def task(self, task_id: str):
        """读取任务执行状态。

        Args:
            task_id: 任务标识。
        """
        async with self.sessions() as session:
            return await session.get(DeviceTask, task_id)

    async def cancel(self, task_id: str):
        """持久化取消意图，由客户端确认实际结果。

        Args:
            task_id: 已校验权限的任务标识。
        """
        async with self.sessions() as session:
            await session.exec(update(DeviceTask).where(DeviceTask.id == task_id, DeviceTask.status.not_in(TERMINAL)).values(cancel_requested=True))
            await session.commit()

    async def event(self, device_id: str, connection_id: str, event: DeviceEventRequest):
        """按单调序号落库执行输出，结束结果不可被迟到事件覆盖。

        Args:
            device_id: 已鉴权设备。
            connection_id: 当前连接。
            event: 客户端任务事件。
        """
        async with self.sessions() as session:
            device = (await session.exec(select(Device).where(Device.id == device_id, Device.connection_id == connection_id, Device.revoked == False).with_for_update())).first()  # noqa: E712
            if device is None:
                raise ValueError("设备连接已失效")
            task = (await session.exec(select(DeviceTask).where(DeviceTask.id == event.task_id, DeviceTask.device_id == device_id).with_for_update())).first()
            if task is None:
                raise ValueError("任务不存在")
            if task.status not in TERMINAL and event.sequence > task.sequence:
                task.sequence = event.sequence
                task.status = event.status
                task.output = (task.output + event.output)[-131072:]
                task.result = event.result
                session.add(task)
                await session.commit()


_store: DeviceStore | None = None


async def close_device_store():
    """关闭已经创建的设备连接池，不触发数据库初始化。

    Args:
        无。
    """
    global _store
    if _store is not None:
        await _store.engine.dispose()
        _store = None


def get_device_store() -> DeviceStore:
    """返回延迟初始化的设备存储。

    Args:
        无。
    """
    global _store
    if _store is None:
        from deepclaw.constant import HOME_PATH
        Path(HOME_PATH).mkdir(parents=True, exist_ok=True)
        _store = DeviceStore()
    return _store

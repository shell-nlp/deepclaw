from sqlmodel import select

from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.auth.rbac.models import RbacPolicyRule, RbacRoleRule
from deepclaw.web_backend.db import resolve_metadata_db_url

_store: "RbacPolicyStore | None" = None


class RbacPolicyStore:
    """RBAC 策略持久化存储。

    Args:
        db_url: 数据库连接地址；为空时使用元数据数据库（默认 .deepclaw/rbac.db）。
    """

    def __init__(self, db_url: str | None = None) -> None:
        from sqlalchemy.pool import NullPool

        # 策略可能在任何事件循环中读取，NullPool 避免连接绑定到已关闭的循环。
        self.engine = create_async_engine_from_url(
            db_url or resolve_metadata_db_url("rbac.db"),
            poolclass=NullPool,
        )
        self.sessions = build_async_sessionmaker(self.engine)

    async def ensure_schema(self) -> None:
        """创建策略相关数据表，已存在时跳过。

        Args:
            无。
        """
        from sqlmodel import SQLModel

        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def is_initialized(self) -> bool:
        """判断策略表是否已经写入过基础策略。

        Args:
            无。

        Returns:
            bool: 存在任一策略行时返回真。
        """
        async with self.sessions() as session:
            policy_exists = (await session.exec(select(RbacPolicyRule).limit(1))).first() is not None
            role_exists = (await session.exec(select(RbacRoleRule).limit(1))).first() is not None
        return policy_exists or role_exists

    async def list_policies(self) -> list[RbacPolicyRule]:
        """列出全部策略行。

        Args:
            无。

        Returns:
            list[RbacPolicyRule]: 按主体和路径排序的策略行。
        """
        async with self.sessions() as session:
            return list(
                (
                    await session.exec(
                        select(RbacPolicyRule).order_by(
                            RbacPolicyRule.subject,
                            RbacPolicyRule.path,
                            RbacPolicyRule.action,
                        )
                    )
                ).all()
            )

    async def list_roles(self) -> list[RbacRoleRule]:
        """列出全部角色继承行。

        Args:
            无。

        Returns:
            list[RbacRoleRule]: 按父子角色排序的继承行。
        """
        async with self.sessions() as session:
            return list(
                (
                    await session.exec(
                        select(RbacRoleRule).order_by(RbacRoleRule.child, RbacRoleRule.parent)
                    )
                ).all()
            )

    async def seed(self, policies: list[tuple[str, str, str]], roles: list[tuple[str, str]]) -> None:
        """把基础策略写入空库。

        Args:
            policies: (主体, 路径, 动作) 三元组列表。
            roles: (子角色, 父角色) 二元组列表。
        """
        async with self.sessions() as session:
            for subject, path, action in policies:
                session.add(RbacPolicyRule(subject=subject, path=path, action=action))
            for child, parent in roles:
                session.add(RbacRoleRule(child=child, parent=parent))
            await session.commit()

    async def add_policy(self, subject: str, path: str, action: str) -> RbacPolicyRule:
        """新增一条策略行，重复时返回已有行。

        Args:
            subject: 策略主体。
            path: 资源路径。
            action: 动作名称。

        Returns:
            RbacPolicyRule: 新增或已存在的策略行。
        """
        async with self.sessions() as session:
            existing = (
                await session.exec(
                    select(RbacPolicyRule).where(
                        RbacPolicyRule.subject == subject,
                        RbacPolicyRule.path == path,
                        RbacPolicyRule.action == action,
                    )
                )
            ).first()
            if existing is not None:
                return existing
            rule = RbacPolicyRule(subject=subject, path=path, action=action)
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    async def delete_policy(self, subject: str, path: str, action: str) -> bool:
        """删除一条策略行。

        Args:
            subject: 策略主体。
            path: 资源路径。
            action: 动作名称。

        Returns:
            bool: 删除成功时返回真。
        """
        async with self.sessions() as session:
            rule = (
                await session.exec(
                    select(RbacPolicyRule).where(
                        RbacPolicyRule.subject == subject,
                        RbacPolicyRule.path == path,
                        RbacPolicyRule.action == action,
                    )
                )
            ).first()
            if rule is None:
                return False
            await session.delete(rule)
            await session.commit()
            return True

    async def add_role(self, child: str, parent: str) -> RbacRoleRule:
        """新增一条角色继承行，重复时返回已有行。

        Args:
            child: 子角色或被赋予角色的用户 ID。
            parent: 父角色。

        Returns:
            RbacRoleRule: 新增或已存在的继承行。
        """
        async with self.sessions() as session:
            existing = (
                await session.exec(
                    select(RbacRoleRule).where(
                        RbacRoleRule.child == child,
                        RbacRoleRule.parent == parent,
                    )
                )
            ).first()
            if existing is not None:
                return existing
            rule = RbacRoleRule(child=child, parent=parent)
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    async def delete_role(self, child: str, parent: str) -> bool:
        """删除一条角色继承行。

        Args:
            child: 子角色或被赋予角色的用户 ID。
            parent: 父角色。

        Returns:
            bool: 删除成功时返回真。
        """
        async with self.sessions() as session:
            rule = (
                await session.exec(
                    select(RbacRoleRule).where(
                        RbacRoleRule.child == child,
                        RbacRoleRule.parent == parent,
                    )
                )
            ).first()
            if rule is None:
                return False
            await session.delete(rule)
            await session.commit()
            return True


def run_store_sync(coro):
    """在独立事件循环中执行存储协程，供同步的 Casbin 装载逻辑调用。

    已有运行中的事件循环时（例如异步测试上下文），新建线程执行，
    避免与当前循环的协程互相等待。

    Args:
        coro: 待执行的存储协程。

    Returns:
        协程执行结果。
    """
    import asyncio
    import threading

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[object] = []
    error: list[BaseException] = []

    def runner() -> None:
        """在新线程的独立事件循环中执行协程。

        Args:
            无。
        """
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001 - 需要把异常传回调用线程
            error.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0] if result else None


def get_rbac_policy_store() -> RbacPolicyStore:
    """返回延迟初始化的 RBAC 策略存储。

    Args:
        无。

    Returns:
        RbacPolicyStore: 进程内共享的策略存储。
    """
    global _store
    if _store is None:
        _store = RbacPolicyStore()
    return _store


async def close_rbac_policy_store() -> None:
    """释放策略存储连接池。

    Args:
        无。
    """
    global _store
    if _store is not None:
        await _store.engine.dispose()
        _store = None

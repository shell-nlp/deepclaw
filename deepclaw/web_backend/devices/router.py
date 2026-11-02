"""设备配对、用户管理与客户端连接入口。"""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from deepclaw.web_backend.auth.dependencies import CurrentActor, require_authenticated_actor
from deepclaw.web_backend.devices.installer import router as installer_router
from deepclaw.web_backend.devices.schemas import (
    DeviceResponse, DeviceListResponse, DeviceTaskResponse, DeviceTaskListResponse,
    PairingClaimRequest, PairingClaimResponse, PairingResponse, DevicePolicyRequest, DeviceEventRequest,
)
from deepclaw.web_backend.devices.store import DeviceStore, get_device_store, ONLINE_SECONDS

router = APIRouter(prefix="/api/devices", tags=["devices"])
router.include_router(installer_router)


def device_response(device) -> DeviceResponse:
    """转换用户设备状态，不返回认证凭据。

    Args:
        device: 持久化设备。
    """
    online = bool(device.connection_id and device.last_seen > time.time() - ONLINE_SECONDS)
    return DeviceResponse(id=device.id, name=device.name, platform=device.platform, online=online,
                          enabled=online and device.enabled, revision=device.revision,
                          capabilities=device.capabilities, roots=device.roots, last_seen=device.last_seen)


def task_response(task) -> DeviceTaskResponse:
    """转换任务执行记录。

    Args:
        task: 持久化任务。
    """
    return DeviceTaskResponse(**task.model_dump())


@router.get("", response_model=DeviceListResponse)
async def list_devices(actor: CurrentActor = Depends(require_authenticated_actor), store: DeviceStore = Depends(get_device_store)):
    """查询当前用户设备，管理员也不能越过设备归属。

    Args:
        actor: 已认证用户。
        store: 设备存储。
    """
    return DeviceListResponse(items=[device_response(device) for device in await store.devices(actor.user_id)])


@router.post("/pairings", response_model=PairingResponse)
async def create_pairing(actor: CurrentActor = Depends(require_authenticated_actor), store: DeviceStore = Depends(get_device_store)):
    """创建供桌面客户端输入的短期配对码。

    Args:
        actor: 已认证用户。
        store: 设备存储。
    """
    code, expires = await store.pair(actor.user_id)
    return PairingResponse(code=code, expires_at=expires)


@router.post("/pairings/claim", response_model=PairingClaimResponse)
async def claim_pairing(request: PairingClaimRequest, store: DeviceStore = Depends(get_device_store)):
    """一次性领取设备凭据，高熵配对码不进入 URL。

    Args:
        request: 配对码及设备名称。
        store: 设备存储。
    """
    try:
        device_id, token = await store.claim(request.code, request.name.strip(), request.platform)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return PairingClaimResponse(device_id=device_id, token=token)


@router.delete("/{device_id}", status_code=204)
async def revoke_device(device_id: str, actor: CurrentActor = Depends(require_authenticated_actor), store: DeviceStore = Depends(get_device_store)):
    """解绑自己的设备并撤销其连接凭据。

    Args:
        device_id: 设备标识。
        actor: 已认证用户。
        store: 设备存储。
    """
    if await store.device(device_id, actor.user_id) is None:
        raise HTTPException(404, "设备不存在")
    await store.revoke(device_id, actor.user_id)


@router.get("/{device_id}/tasks", response_model=DeviceTaskListResponse)
async def list_tasks(device_id: str, actor: CurrentActor = Depends(require_authenticated_actor), store: DeviceStore = Depends(get_device_store)):
    """查询当前用户设备的最近任务。

    Args:
        device_id: 设备标识。
        actor: 已认证用户。
        store: 设备存储。
    """
    if await store.device(device_id, actor.user_id) is None:
        raise HTTPException(404, "设备不存在")
    return DeviceTaskListResponse(items=[task_response(task) for task in await store.tasks(device_id)])


@router.post("/{device_id}/tasks/{task_id}/cancel", response_model=DeviceTaskResponse)
async def cancel_task(device_id: str, task_id: str, actor: CurrentActor = Depends(require_authenticated_actor), store: DeviceStore = Depends(get_device_store)):
    """请求取消任务，等待客户端报告实际终止结果。

    Args:
        device_id: 设备标识。
        task_id: 任务标识。
        actor: 已认证用户。
        store: 设备存储。
    """
    task = await store.task(task_id)
    if task is None or task.device_id != device_id or task.owner_user_id != actor.user_id:
        raise HTTPException(404, "任务不存在")
    await store.cancel(task_id)
    return task_response(await store.task(task_id))


@router.websocket("/connect")
async def device_connection(websocket: WebSocket, store: DeviceStore = Depends(get_device_store)):
    """设备凭据鉴权的单连接队列，数据库路由支持多实例。

    Args:
        websocket: 桌面客户端连接。
        store: 共享设备存储。
    """
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    device = await store.authenticate(token) if scheme.lower() == "bearer" else None
    if device is None:
        await websocket.close(code=4401)
        return
    connection_id = uuid.uuid4().hex
    if not await store.connect(device.id, connection_id):
        await websocket.close(code=4409)
        return
    await websocket.accept()
    await websocket.send_json({"type": "welcome", "device_id": device.id, "revision": device.revision})
    sent = {}
    checked_at = 0
    received_at = time.monotonic()
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1)
                if len(raw) > 2097152:
                    await websocket.close(code=4400)
                    return
                message = json.loads(raw)
                received_at = time.monotonic()
                if message.get("type") == "policy":
                    await store.policy(device.id, connection_id, DevicePolicyRequest.model_validate(message))
                    await websocket.send_json({"type": "policy_ack", "revision": message["revision"]})
                elif message.get("type") == "task_event":
                    event = DeviceEventRequest.model_validate(message)
                    await store.event(device.id, connection_id, event)
                    await websocket.send_json({"type": "event_ack", "task_id": event.task_id, "sequence": event.sequence})
                elif message.get("type") != "ping":
                    raise ValueError("未知设备协议消息")
            except TimeoutError:
                pass
            if time.monotonic() - received_at > 25:
                await websocket.close(code=4408)
                return
            if time.monotonic() - checked_at > 5:
                if not await store.heartbeat(device.id, connection_id):
                    await websocket.close(code=4401)
                    return
                checked_at = time.monotonic()
            current = await store.device(device.id)
            if current is None or current.connection_id != connection_id:
                await websocket.close(code=4401)
                return
            for task in reversed(await store.tasks(device.id, active=True)):
                cancel = task.cancel_requested or task.expires_at <= time.time() or task.revision != current.revision or not current.enabled
                marker = (cancel, task.sequence)
                if sent.get(task.id) == marker:
                    continue
                if cancel:
                    await websocket.send_json({"type": "cancel", "task_id": task.id, "revision": task.revision,
                        "operation": task.operation, "arguments": task.arguments, "expires_at": task.expires_at})
                else:
                    await websocket.send_json({"type": "execute", "task_id": task.id, "revision": task.revision,
                        "operation": task.operation, "arguments": task.arguments, "expires_at": task.expires_at})
                sent[task.id] = marker
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (ValueError, ValidationError, TypeError):
        await websocket.close(code=4400)
    finally:
        await store.disconnect(device.id, connection_id)

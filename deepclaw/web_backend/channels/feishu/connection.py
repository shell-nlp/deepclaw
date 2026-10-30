"""隔离飞书 SDK 的模块级事件循环，每个绑定使用可终止的独立进程。"""

import asyncio
import multiprocessing
from queue import Empty

from deepclaw.web_backend.channels.models import ChannelBinding


def normalize_event(data):
    """把 SDK 消息转换成可跨进程传递的普通字典。

    Args:
        data: SDK 消息对象或测试字典。
    """
    root = getattr(data, "event", None)
    if root is None:
        return data if isinstance(data, dict) else None
    message = getattr(root, "message", None)
    sender = getattr(getattr(root, "sender", None), "sender_id", None)
    mentions = []
    for mention in getattr(message, "mentions", None) or []:
        identifier = getattr(mention, "id", None)
        mentions.append({"id": {"open_id": getattr(identifier, "open_id", None)}})
    return {"message_id": getattr(message, "message_id", None),
            "chat_id": getattr(message, "chat_id", None), "chat_type": getattr(message, "chat_type", None),
            "message_type": getattr(message, "message_type", None), "content": getattr(message, "content", None),
            "sender": {"sender_id": {"open_id": getattr(sender, "open_id", None),
                                     "user_id": getattr(sender, "user_id", None)}}, "mentions": mentions}


def run_sdk_process(binding_data, queue, acknowledgements):
    """在子进程内运行官方 SDK，其全局事件循环仅属于当前绑定。

    Args:
        binding_data: 序列化绑定配置。
        queue: 有界父进程通知队列。
        acknowledgements: 父进程持久化成功的确认队列。
    """
    from deepclaw.web_backend.channels.feishu.client import FeishuClientGateway

    gateway = FeishuClientGateway()
    lark = gateway._import_lark()
    binding = ChannelBinding.model_validate(binding_data)

    def on_message(data):
        """把消息提交到父进程。

        Args:
            data: SDK 回调对象。
        """
        event = normalize_event(data)
        if event is not None:
            queue.put(("message", event))
            acknowledgements.get(timeout=30)

    handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(on_message).build()
    client = gateway.build_ws_client(binding=binding, event_handler=handler)
    original_connect = client._connect

    async def connect():
        """仅在真实握手成功后通知已连接。

        Args:
            无。
        """
        await original_connect()
        queue.put(("status", "connected"))

    def reconnecting():
        """通知父进程连接已断开。

        Args:
            无。
        """
        queue.put(("status", "reconnecting"))

    client._connect = connect
    client.on_reconnecting = reconnecting
    try:
        client.start()
    finally:
        queue.put(("status", "error"))


async def run_connection(binding, on_event, on_status):
    """监管连接子进程，取消时关闭连接及跨进程通信资源。

    Args:
        binding: 当前绑定。
        on_event: 父进程异步消息接收器。
        on_status: 父进程异步连接状态接收器。
    """
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(maxsize=256)
    acknowledgements = context.Queue(maxsize=1)
    process = context.Process(target=run_sdk_process, args=(binding.model_dump(), queue, acknowledgements), daemon=True)
    process.start()
    try:
        while True:
            for _ in range(50):
                try:
                    kind, value = queue.get_nowait()
                except Empty:
                    break
                if kind == "message":
                    await on_event(value)
                    acknowledgements.put_nowait(True)
                else:
                    await on_status(value)
            if not process.is_alive():
                raise ConnectionError("飞书连接进程已退出")
            await asyncio.sleep(0.1)
    finally:
        if process.is_alive():
            process.terminate()
        await asyncio.to_thread(process.join, 3)
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join, 3)
        queue.close()
        queue.cancel_join_thread()
        acknowledgements.close()
        acknowledgements.cancel_join_thread()
        process.close()

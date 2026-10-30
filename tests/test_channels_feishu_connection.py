"""飞书连接进程的通知、持久化确认及取消清理测试。"""

import asyncio
from queue import Empty

import pytest

from deepclaw.web_backend.channels.feishu import connection
from deepclaw.web_backend.channels.models import ChannelBinding


def test_connection_persists_before_ack_and_reclaims_process(monkeypatch):
    """消息先持久化再确认，取消后终止并回收进程及队列。

    Args:
        monkeypatch: 隔离进程与队列。
    """
    acknowledgements = []
    queues = []
    processed = asyncio.Event()

    class Queue:
        """可检查资源关闭的队列。"""

        def __init__(self, items):
            """初始化消息。

            Args:
                items: 队列初始消息。
            """
            self.items, self.closed = items, False

        def get_nowait(self):
            """读取下一条消息。

            Args:
                无。
            """
            if not self.items:
                raise Empty
            return self.items.pop(0)

        def put_nowait(self, value):
            """验证持久化先于确认。

            Args:
                value: 确认值。
            """
            assert processed.is_set()
            acknowledgements.append(value)

        def close(self):
            """记录关闭。

            Args:
                无。
            """
            self.closed = True

        def cancel_join_thread(self):
            """模拟队列线程退出。

            Args:
                无。
            """

    class Process:
        """可检查停止回收的连接进程。"""

        alive = True
        closed = False
        joined = False

        def start(self):
            """模拟启动。

            Args:
                无。
            """

        def is_alive(self):
            """返回运行状态。

            Args:
                无。
            """
            return self.alive

        def terminate(self):
            """模拟终止连接。

            Args:
                无。
            """
            self.alive = False

        def join(self, timeout):
            """记录等待回收。

            Args:
                timeout: 最长等待秒数。
            """
            self.joined = True

        def close(self):
            """记录进程句柄关闭。

            Args:
                无。
            """
            self.closed = True

    process = Process()

    class Context:
        """提供隔离进程与通知队列。"""

        def Queue(self, maxsize):
            """创建有界队列。

            Args:
                maxsize: 最大队列长度。
            """
            queue = Queue([("message", {"message_id": "m"})] if not queues else [])
            queues.append(queue)
            return queue

        def Process(self, **kwargs):
            """返回假进程。

            Args:
                kwargs: 进程配置。
            """
            assert kwargs["daemon"] is True
            return process

    monkeypatch.setattr(connection.multiprocessing, "get_context", lambda mode: Context())

    async def run():
        """执行消息确认和取消场景。

        Args:
            无。
        """
        async def on_event(event):
            """模拟消息已经持久化。

            Args:
                event: 消息事件。
            """
            processed.set()

        async def on_status(status):
            """忽略本测试中的状态事件。

            Args:
                status: 连接状态。
            """

        binding = ChannelBinding(id=1, channel="feishu", owner_user_id="u", manager_user_id="u")
        task = asyncio.create_task(connection.run_connection(binding, on_event, on_status))
        await asyncio.wait_for(processed.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert acknowledgements == [True]
    assert process.closed and process.joined and not process.alive
    assert all(queue.closed for queue in queues)

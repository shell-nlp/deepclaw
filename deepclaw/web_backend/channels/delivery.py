"""隔离渠道投递异常，保证发送失败后仍收集 Agent 最终结果。"""


class DurableChannelAdapter:
    """保存回复标识并隔离发送异常的适配器。"""

    def __init__(self, adapter, job, jobs):
        """初始化投递状态。

        Args:
            adapter: 真实适配器。
            job: 持久化任务。
            jobs: 任务存储。
        """
        self.adapter, self.job, self.jobs = adapter, job, jobs
        self.failed = False
        self.supports_message_stream = getattr(adapter, "supports_message_stream", True)

    async def send_message(self, message, text):
        """发送或更新回复，发送前持久化投递意图。

        Args:
            message: 入站消息。
            text: 待发送正文。
        """
        if self.failed:
            return self.job.reply_id or self.job.id
        self.job.delivery_status = "sending"
        await self.jobs.save(self.job)
        try:
            send_once = getattr(self.adapter, "send_message_once", None)
            if self.job.reply_id and self.supports_message_stream:
                await self.adapter.edit_message(self.job.reply_id, text)
            elif send_once is not None:
                self.job.reply_id = await send_once(message, text, self.job.id)
            else:
                self.job.reply_id = await self.adapter.send_message(message, text)
        except NotImplementedError:
            self.failed = True
            self.job.delivery_status = "failed"
            self.job.error = "该渠道尚未接入消息发送，结果已保留"
            await self.jobs.save(self.job)
            return self.job.id
        except Exception:
            await self._fail("渠道回复发送失败")
            return self.job.reply_id or self.job.id
        self.job.delivery_status = "pending"
        await self.jobs.save(self.job)
        return self.job.reply_id

    async def _fail(self, error):
        """记录发送结果，无法安全重试的发送标为待人工核对。

        Args:
            error: 脱敏错误提示。
        """
        self.failed = True
        safe = self.job.reply_id is not None or hasattr(self.adapter, "send_message_once")
        self.job.delivery_status = "failed" if safe else "uncertain"
        self.job.error = error if safe else "渠道发送结果不确定，需要人工核对"
        await self.jobs.save(self.job)

    async def start_message(self, message, text):
        """复用已有回复或首次发送占位消息。

        Args:
            message: 入站消息。
            text: 占位提示。
        """
        return self.job.reply_id or await self.send_message(message, text)

    async def edit_message(self, reply_message_id, text):
        """更新回复而不让渠道故障中断 Agent。

        Args:
            reply_message_id: 回复标识。
            text: 正文。
        """
        if not self.failed:
            try:
                await self.adapter.edit_message(reply_message_id, text)
            except Exception:
                await self._fail("渠道回复更新失败")

    async def finish_message(self, reply_message_id, text):
        """执行可选的回复完成操作。

        Args:
            reply_message_id: 回复标识。
            text: 最终正文。
        """
        method = getattr(self.adapter, "finish_message", None)
        if method is not None and not self.failed:
            try:
                await method(reply_message_id, text)
            except Exception:
                await self._fail("渠道回复完成操作失败")

    async def start_typing(self, message):
        """尽力展示输入状态。

        Args:
            message: 入站消息。
        """
        await self._typing("start_typing", message)

    async def stop_typing(self, message):
        """尽力清理输入状态。

        Args:
            message: 入站消息。
        """
        await self._typing("stop_typing", message)

    async def _typing(self, name, message):
        """忽略不影响业务回复的输入状态故障。

        Args:
            name: 输入状态方法名。
            message: 入站消息。
        """
        method = getattr(self.adapter, name, None)
        if method is not None:
            try:
                await method(message)
            except Exception:
                pass

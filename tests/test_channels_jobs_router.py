"""渠道消息恢复接口权限和操作语义测试。"""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.jobs import ChannelJobStore
from deepclaw.web_backend.channels.models import ChannelMessage
from deepclaw.web_backend.channels.router import router
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


def test_job_management_hides_payload_and_checks_owner(tmp_path):
    """任务列表不泄露原始消息和凭据，其他用户不能操作。

    Args:
        tmp_path: 隔离数据库目录。
    """
    store = ChannelStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    jobs = ChannelJobStore(store)

    async def prepare():
        """准备已执行、待投递任务。

        Args:
            无。
        """
        job = await jobs.enqueue(ChannelMessage(channel="feishu", message_id="m", channel_user_id="ou",
                                               channel_conversation_id="chat", user_id="owner", text="私密正文",
                                               raw={"context_token": "secret"}))
        job.execution_status, job.delivery_status = "completed", "failed"
        job.text = "私密结果"
        job.error = "发送失败"
        await jobs.save(job)
        return job

    job = asyncio.run(prepare())
    actor = CurrentActor(is_guest=False, user_id="other", email=None, role="user")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_channel_store] = lambda: store
    app.dependency_overrides[get_current_actor] = lambda: actor
    try:
        with TestClient(app) as client:
            assert client.get("/api/channels/jobs").json()["items"] == []
            assert client.get("/api/channels/jobs?scope=all").status_code == 403
            assert client.post(f"/api/channels/jobs/{job.id}/actions", json={"action": "retry_delivery"}).status_code == 404
            actor.user_id = "owner"
            response = client.get("/api/channels/jobs")
            assert len(response.json()["items"]) == 1
            assert "secret" not in response.text
            assert "私密" not in response.text
            assert client.post(f"/api/channels/jobs/{job.id}/actions", json={"action": "retry_delivery"}).status_code == 200
            assert asyncio.run(jobs.get(job.id)).run_id == job.run_id
    finally:
        asyncio.run(store.engine.dispose())


def test_manual_resolution_does_not_create_run_or_replay_tools(tmp_path):
    """人工核对只结束异常任务，原 Run 标识保留。

    Args:
        tmp_path: 隔离数据库目录。
    """
    store = ChannelStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    jobs = ChannelJobStore(store)

    async def prepare():
        """准备 Run 丢失任务。

        Args:
            无。
        """
        job = await jobs.enqueue(ChannelMessage(channel="feishu", message_id="m", channel_user_id="u",
                                               channel_conversation_id="c", text="问题"))
        job.execution_status = "uncertain"
        job.error = "原 Run 已不存在"
        await jobs.save(job)
        return job

    job = asyncio.run(prepare())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_channel_store] = lambda: store
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(is_guest=True, user_id=None, email=None, role="guest")
    try:
        with TestClient(app) as client:
            path = f"/api/channels/jobs/{job.id}/actions"
            assert client.post(path, json={"action": "retry_delivery"}).status_code == 409
            assert client.post(path, json={"action": "close"}).status_code == 200
            saved = asyncio.run(jobs.get(job.id))
            assert saved.run_id == job.run_id
            assert saved.resolved_by == "guest"
            assert saved.resolved_at is not None
            assert saved.execution_status == "failed"
    finally:
        asyncio.run(store.engine.dispose())

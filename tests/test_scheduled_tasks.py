import asyncio
import importlib
import os
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.middleware.cron.schedule_store import ScheduleStore, next_occurrence, utc_now
from deepclaw.middleware.cron.schemas import ScheduleRequest
from deepclaw.web_backend.auth.dependencies import CurrentActor, require_authenticated_actor

POSTGRES_URL = os.getenv("SCHEDULE_TEST_POSTGRES_URL")


@pytest.mark.parametrize(("cron", "expected_seconds"), [
    ("* * * * *", 53),
    ("*/10 * * * * *", 3),
])
def test_cron_precision(cron, expected_seconds):
    """验证旧的分钟表达式和新秒字段的下次执行时间。

    Args:
        cron: 待计算的 Cron 表达式。
        expected_seconds: 距离下一次执行的预期秒数。
    """
    now = datetime(2026, 11, 24, 1, 0, 7)
    settings = ScheduleRequest(name="周期测试", content="提醒", cron=cron)
    assert next_occurrence(settings, now) == now + timedelta(seconds=expected_seconds)


def test_second_interval_keeps_cadence(tmp_path, monkeypatch):
    """验证秒级间隔过期补领后保持原调度节奏，同一任务串行执行。

    Args:
        tmp_path: SQLite 测试目录。
        monkeypatch: 测试时钟替换工具。
    """
    store_module = importlib.import_module("deepclaw.middleware.cron.schedule_store")
    start = datetime(2026, 11, 24, 1)
    now = start
    monkeypatch.setattr(store_module, "utc_now", lambda: now)

    async def run():
        """通过数据库验收固定间隔任务。

        Args:
            无。
        """
        nonlocal now
        store = ScheduleStore(f"sqlite:///{tmp_path / 'interval.db'}")
        try:
            task = await store.save("owner", ScheduleRequest(
                name="十秒提醒", content="提醒", interval_seconds=10,
            ))
            assert task.next_at == (start + timedelta(seconds=10)).replace(tzinfo=UTC)
            assert await store.claim() is None
            now = start + timedelta(seconds=32)
            claimed, _ = await store.claim()
            assert claimed.scheduled_at == start + timedelta(seconds=10)
            assert (await store.list_jobs("owner"))[0].next_at == (
                start + timedelta(seconds=40)
            ).replace(tzinfo=UTC)
            now = start + timedelta(seconds=41)
            assert await store.claim() is None
            assert await store.finish(claimed, status="succeeded", message="提醒")
            following, _ = await store.claim()
            assert following.scheduled_at == start + timedelta(seconds=40)
        finally:
            await store.engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("backend", [
    "sqlite", pytest.param("postgresql", marks=pytest.mark.skipif(
        not POSTGRES_URL, reason="需要临时 PostgreSQL 测试库"
    )),
])
def test_workers_deliver_once_and_share_results(backend, tmp_path, monkeypatch):
    """验证两个 worker 原子领取，结果可鉴权下载且保持账号隔离。

    Args:
        backend: 被验证的数据库类型。
        tmp_path: SQLite 和对象存储目录。
        monkeypatch: 测试替换工具。
    """
    from deepclaw.middleware.cron import executor
    from deepclaw.web_backend import schedules
    from deepclaw.web_backend.auth.rbac import dependencies as rbac_dependencies

    store_module = importlib.import_module("deepclaw.middleware.cron.schedule_store")
    url = POSTGRES_URL if backend == "postgresql" else f"sqlite:///{tmp_path / 'shared.db'}"
    store = ScheduleStore(url)
    second_store = ScheduleStore(url)
    monkeypatch.setattr(executor.settings, "OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setattr(executor.settings, "LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setattr(schedules, "get_schedule_store", lambda: store)

    async def active_user(user_id):
        """模拟执行任务时查到有效账号。

        Args:
            user_id: 执行者账号。
        """
        return SimpleNamespace(is_active=True)

    monkeypatch.setattr(executor, "get_auth_service", lambda: SimpleNamespace(
        store=SimpleNamespace(get_user_by_user_id=active_user)
    ))
    owner = SimpleNamespace(id="owner")
    grants = {"read", "write"}

    def is_allowed(actor, *, path, action, owner):
        """为定时任务测试提供可撤销的角色权限。

        Args:
            actor: 当前测试账号。
            path: 授权功能路径。
            action: 授权动作。
            owner: 资源归属。
        """
        return path == "/api/schedules" and action in grants

    monkeypatch.setattr(rbac_dependencies, "is_allowed", is_allowed)

    def current_actor():
        """返回当前登录账号。

        Args:
            无。
        """
        return CurrentActor(is_guest=False, user_id=owner.id, email=None, role="user")

    app = FastAPI()
    app.dependency_overrides[require_authenticated_actor] = current_actor
    app.include_router(schedules.router)
    now = utc_now()
    run_at = (now + timedelta(seconds=10)).replace(tzinfo=UTC)
    with TestClient(app) as client:
        grants.remove("read")
        assert client.get("/api/schedules").status_code == 403
        assert client.get("/api/schedules/notifications").status_code == 403
        grants.add("read")
        grants.remove("write")
        assert client.get("/api/schedules").status_code == 200
        assert client.post("/api/schedules", json={
            "name": "未授权任务", "content": "测试", "interval_seconds": 10,
        }).status_code == 403
        grants.add("write")
        for output in ("notification", "md", "docx"):
            task = ScheduleRequest(name="中文通知", content="测试正文", run_at=run_at, output=output)
            res = client.post("/api/schedules", json=task.model_dump(mode="json"))
            assert res.status_code == 201, res.text
        jobs = client.get("/api/schedules").json()
        assert len(jobs) == 3
        job_id = jobs[0]["id"]
        enabled_path = "/api/schedules/" + job_id + "/enabled"
        paused = client.patch(enabled_path, json={"enabled": False})
        assert paused.status_code == 200
        assert paused.json()["next_at"] is None
        owner.id = "other"
        assert client.patch(enabled_path, json={"enabled": True}).status_code == 404
        assert client.delete("/api/schedules/" + job_id).status_code == 404
        assert client.get("/api/schedules").json() == []
        owner.id = "owner"
        started = client.patch(enabled_path, json={"enabled": True})
        assert started.status_code == 200
        assert started.json()["next_at"]

        monkeypatch.setattr(store_module, "utc_now", lambda: now + timedelta(seconds=11))

        async def execute():
            """在两个连接池间竞争领取并投递所有到期任务。

            Args:
                无。
            """
            delivered = set()
            while len(delivered) < 3:
                results = await asyncio.gather(store.claim(), second_store.claim())
                claims = [result for result in results if result is not None]
                assert claims
                for run, settings in claims:
                    assert run.job_id not in delivered
                    delivered.add(run.job_id)
                    await executor.deliver(store, run, settings)
            assert await store.claim() is None
            await store.engine.dispose()
            await second_store.engine.dispose()

        client.portal.call(execute)
        payload = client.get("/api/schedules/notifications").json()
        assert payload["unread"] == 3
        for item in payload["items"]:
            assert item["status"] == "succeeded", item
            assert item["scheduled_at"] and item["finished_at"]
            if not item["filename"]:
                assert item["message"] == "测试正文"
                continue
            path = "/api/schedules/notifications/" + item["id"] + "/file"
            response = client.get(path)
            assert response.status_code == 200
            if item["filename"].endswith(".md"):
                assert response.text == "测试正文"
            else:
                assert Document(BytesIO(response.content)).paragraphs[0].text == "测试正文"
            owner.id = "other"
            assert client.get(path).status_code == 404
            owner.id = "owner"
        ids = [item["id"] for item in payload["items"]]
        assert client.post("/api/schedules/notifications/read", json={"ids": ids}).status_code == 204
        assert client.get("/api/schedules/notifications").json()["unread"] == 0
        assert client.delete("/api/schedules/" + job_id).status_code == 204
        assert len(client.get("/api/schedules/notifications").json()["items"]) == 3
        attachment = next(item for item in payload["items"] if item["filename"])
        notification_path = "/api/schedules/notifications/" + attachment["id"]
        owner.id = "other"
        assert client.delete(notification_path).status_code == 404
        owner.id = "owner"
        assert client.delete(notification_path).status_code == 204
        assert client.get(notification_path + "/file").status_code == 404
        assert len(client.get("/api/schedules/notifications").json()["items"]) == 2
        assert len(list((tmp_path / "objects").rglob("*.md")) +
                   list((tmp_path / "objects").rglob("*.docx"))) == 1
        client.portal.call(store.engine.dispose)


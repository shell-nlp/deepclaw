from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.auth.service import AuthService, get_auth_service
from deepclaw.web_backend.auth.store import AuthStore
from deepclaw.web_backend.common.endpoints import (
    GUEST_USER_ID,
    add_general_api_endpoint,
)


class DummyContext(BaseModel):
    user_id: str = "default"


class DummyAgent:
    def __init__(self):
        self.contexts: list[DummyContext] = []

    async def astream(self, *, context, **kwargs):
        self.contexts.append(context)
        if False:
            yield None


def build_client(actor: CurrentActor) -> tuple[TestClient, DummyAgent]:
    app = FastAPI()
    agent = DummyAgent()
    add_general_api_endpoint(
        app=app,
        agent=agent,
        path="/api/test/general_api",
        context=DummyContext,
        name="test_general_api",
        tags=["tests"],
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    return TestClient(app), agent


def test_general_api_guest_uses_fixed_guest_user_id():
    client, agent = build_client(
        CurrentActor(is_guest=True, user_id=None, email=None, role="guest")
    )

    response = client.post(
        "/api/test/general_api",
        json={"query": "hello", "session_id": "session-1", "user_id": "spoofed", "stream": True},
    )

    assert response.status_code == 200
    assert len(agent.contexts) == 1
    assert agent.contexts[0].user_id == GUEST_USER_ID


def test_general_api_authenticated_actor_overrides_request_user_id():
    client, agent = build_client(
        CurrentActor(
            is_guest=False,
            user_id="user_real_123",
            email="user@example.com",
            role="user",
        )
    )

    response = client.post(
        "/api/test/general_api",
        json={"query": "hello", "session_id": "session-2", "user_id": "spoofed", "stream": True},
    )

    assert response.status_code == 200
    assert len(agent.contexts) == 1
    assert agent.contexts[0].user_id == "user_real_123"


def test_general_api_accepts_internal_user_token():
    service = AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_email=None,
        admin_password=None,
        token_expire_days=30,
    )
    user = service.register(email="channel-user@example.com", password="secret-123")

    app = FastAPI()
    agent = DummyAgent()
    add_general_api_endpoint(
        app=app,
        agent=agent,
        path="/api/test/general_api",
        context=DummyContext,
        name="test_general_api",
        tags=["tests"],
    )
    issued = service.issue_user_access_token(user_id=user.user_id)
    app.dependency_overrides[get_auth_service] = lambda: service
    client = TestClient(app)

    response = client.post(
        "/api/test/general_api",
        json={
            "query": "hello",
            "session_id": "session-3",
            "user_id": "spoofed",
            "stream": True,
        },
        headers={"Authorization": f"Bearer {issued.token}"},
    )

    assert response.status_code == 200
    assert len(agent.contexts) == 1
    assert agent.contexts[0].user_id == user.user_id

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from langchain_api.web_backend.auth.dependencies import CurrentActor, get_current_actor
from langchain_api.web_backend.common.endpoints import (
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

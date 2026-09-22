import asyncio
import importlib

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import httpx
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.models import ChannelMessageRecord
from deepclaw.web_backend.channels.store import ChannelStore


class FakeService:

    def __init__(self):
        self.calls = []

    async def process_message(self, message, adapter):
        self.calls.append((message, adapter))
        return ChannelMessageRecord(channel=message.channel, message_id=message.message_id, channel_conversation_id=message.channel_conversation_id, channel_user_id=message.channel_user_id, status='done')

class FakeWeixinClient:

    async def fetch_login_qrcode(self, *, local_token_list=None):
        self.local_token_list = local_token_list
        return {'qrcode': 'qr-content', 'qrcode_img_content': 'https://example.test/qrcode.png'}

    async def get_qrcode_status(self, *, qrcode, verify_code=None):
        self.qrcode = qrcode
        self.verify_code = verify_code
        return {'status': 'confirmed', 'bot_token': 'token_1', 'baseurl': 'https://node.example.test'}

    async def get_updates(self, *, token, get_updates_buf=''):
        self.token = token
        self.get_updates_buf = get_updates_buf
        return {'get_updates_buf': 'next_buf', 'msgs': [{'message_type': 1, 'message_id': 'wx_msg_1', 'from_user_id': 'wx_user_1', 'context_token': 'ctx_1', 'item_list': [{'text_item': {'text': '你好'}}]}, {'message_type': 2, 'message_id': 'ignored', 'from_user_id': 'wx_user_1', 'context_token': 'ctx_1', 'item_list': [{'text_item': {'text': 'ignore'}}]}]}

class TimeoutWeixinClient:

    async def fetch_login_qrcode(self, *, local_token_list=None):
        raise httpx.ReadTimeout('timed out')

    async def get_qrcode_status(self, *, qrcode, verify_code=None):
        raise httpx.ReadTimeout('timed out')


def build_channels_client(
    *,
    store: ChannelStore,
    actor: CurrentActor | None = None,
    service=None,
    weixin_client=None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    from deepclaw.web_backend.channels.router import router as channels_router
    from deepclaw.web_backend.channels.service import get_channel_service
    from deepclaw.web_backend.channels.store import get_channel_store
    from deepclaw.web_backend.channels.weixin_clawbot.router import (
        get_weixin_clawbot_client,
    )

    app = FastAPI()
    app.include_router(channels_router)
    app.dependency_overrides[get_channel_store] = lambda: store
    if service is not None:
        app.dependency_overrides[get_channel_service] = lambda: service
    if weixin_client is not None:
        app.dependency_overrides[get_weixin_clawbot_client] = lambda: weixin_client
    if actor is not None:
        app.dependency_overrides[get_current_actor] = lambda: actor
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)

def test_channels_router_is_importable_from_nested_business_api_package():
    from deepclaw.web_backend.channels.router import router as channels_router

    assert isinstance(channels_router, APIRouter)


def test_channels_router_assembles_domain_routers():
    from deepclaw.web_backend.channels.dingtalk.router import router as dingtalk_router
    from deepclaw.web_backend.channels.feishu.router import router as feishu_router
    from deepclaw.web_backend.channels.session_router import router as sessions_router
    from deepclaw.web_backend.channels.weixin_clawbot.router import (
        router as weixin_clawbot_router,
    )

    assert isinstance(sessions_router, APIRouter)
    assert isinstance(feishu_router, APIRouter)
    assert isinstance(dingtalk_router, APIRouter)
    assert isinstance(weixin_clawbot_router, APIRouter)


def test_channels_schema_is_importable_from_business_schema_package():
    from deepclaw.web_backend.channels.weixin_clawbot.schemas import (
        WeixinClawBotPollRequest,
    )

    assert 'bot_token' == next(iter(WeixinClawBotPollRequest.model_fields))

def test_legacy_channels_router_module_is_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module('deepclaw.api.routers.channels')


def test_channels_schema_compat_module_is_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module('deepclaw.web_backend.channels.schemas')

def test_session_config_routes_list_and_update_reply_mode():
    store = ChannelStore('sqlite:///:memory:')
    session = asyncio.run(store.get_or_create_session(channel='feishu', channel_conversation_id='chat_a', channel_user_id='ou_1', user_id='user_1', manager_user_id='user_1'))
    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )
    list_response = client.get('/api/channels/sessions')
    assert 200 == list_response.status_code
    assert 1 == list_response.json()['total']
    patch_response = client.patch(f'/api/channels/sessions/{session.session_id}', json={'reply_mode': 'streaming'})
    assert 200 == patch_response.status_code
    assert 'streaming' == patch_response.json()['reply_mode']

def test_session_config_rejects_invalid_reply_mode():
    store = ChannelStore('sqlite:///:memory:')
    session = asyncio.run(store.get_or_create_session(channel='feishu', channel_conversation_id='chat_a', channel_user_id='ou_1', user_id='user_1', manager_user_id='user_1'))
    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )
    response = client.patch(f'/api/channels/sessions/{session.session_id}', json={'reply_mode': 'verbose'})
    assert 422 == response.status_code


def test_session_routes_respect_actor_scope():
    store = ChannelStore('sqlite:///:memory:')
    guest_session = asyncio.run(store.get_or_create_session(
        channel='weixin_clawbot',
        channel_conversation_id='guest:chat_a',
        channel_user_id='guest:wx_1',
        user_id='guest',
        manager_user_id='guest',
    ))
    user_session = asyncio.run(store.get_or_create_session(
        channel='feishu',
        channel_conversation_id='chat_b',
        channel_user_id='ou_2',
        user_id='user_1',
        manager_user_id='user_1',
    ))
    other_session = asyncio.run(store.get_or_create_session(
        channel='feishu',
        channel_conversation_id='chat_c',
        channel_user_id='ou_3',
        user_id='user_2',
        manager_user_id='user_2',
    ))

    guest_client = build_channels_client(
        store=store,
        actor=CurrentActor(is_guest=True, user_id=None, email=None, role='guest'),
    )
    guest_list = guest_client.get('/api/channels/sessions')
    guest_update_other = guest_client.patch(
        f'/api/channels/sessions/{user_session.session_id}',
        json={'reply_mode': 'streaming'},
    )

    assert 200 == guest_list.status_code
    assert [guest_session.session_id] == [item['session_id'] for item in guest_list.json()['items']]
    assert 404 == guest_update_other.status_code

    user_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )
    user_list = user_client.get('/api/channels/sessions')
    user_update_own = user_client.patch(
        f'/api/channels/sessions/{user_session.session_id}',
        json={'reply_mode': 'streaming'},
    )
    user_update_other = user_client.patch(
        f'/api/channels/sessions/{other_session.session_id}',
        json={'reply_mode': 'streaming'},
    )

    assert 200 == user_list.status_code
    assert [user_session.session_id] == [item['session_id'] for item in user_list.json()['items']]
    assert 200 == user_update_own.status_code
    assert 'streaming' == user_update_own.json()['reply_mode']
    assert 404 == user_update_other.status_code


def test_session_routes_allow_admin_override():
    store = ChannelStore('sqlite:///:memory:')
    first = asyncio.run(store.get_or_create_session(
        channel='feishu',
        channel_conversation_id='chat_a',
        channel_user_id='ou_1',
        user_id='user_1',
        manager_user_id='user_1',
    ))
    second = asyncio.run(store.get_or_create_session(
        channel='weixin_clawbot',
        channel_conversation_id='guest:chat_b',
        channel_user_id='guest:wx_2',
        user_id='guest',
        manager_user_id='guest',
    ))

    admin_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='admin_1',
            email='admin@example.com',
            role='admin',
        ),
    )
    list_response = admin_client.get('/api/channels/sessions')
    update_response = admin_client.patch(
        f'/api/channels/sessions/{second.session_id}',
        json={'reply_mode': 'streaming'},
    )

    assert 200 == list_response.status_code
    assert sorted([first.session_id, second.session_id]) == sorted(
        item['session_id'] for item in list_response.json()['items']
    )
    assert 200 == update_response.status_code
    assert 'streaming' == update_response.json()['reply_mode']

def test_feishu_webhook_accepts_normalized_payload():
    store = ChannelStore('sqlite:///:memory:')
    service = FakeService()
    client = build_channels_client(store=store, service=service)
    response = client.post('/api/channels/feishu/events', json={'message_id': 'msg_1', 'channel_user_id': 'ou_1', 'channel_conversation_id': 'chat_a', 'text': 'hello'})
    assert 200 == response.status_code
    assert {'status': 'accepted'} == response.json()
    assert 1 == len(service.calls)
    assert 'feishu' == service.calls[0][0].channel


def test_weixin_clawbot_poll_accepts_text_updates():
    store = ChannelStore('sqlite:///:memory:')
    service = FakeService()
    weixin_client = FakeWeixinClient()
    client = build_channels_client(
        store=store,
        service=service,
        weixin_client=weixin_client,
    )
    response = client.post('/api/channels/weixin-clawbot/poll', json={'bot_token': 'token_1', 'get_updates_buf': 'old_buf'})
    assert 200 == response.status_code
    assert {'status': 'accepted', 'accepted': 1, 'get_updates_buf': 'next_buf'} == response.json()
    assert 'token_1' == weixin_client.token
    assert 'old_buf' == weixin_client.get_updates_buf
    assert 1 == len(service.calls)
    assert 'weixin_clawbot' == service.calls[0][0].channel


def test_binding_list_route_includes_owner_and_manager_participants():
    store = ChannelStore('sqlite:///:memory:')
    asyncio.run(store.create_binding(
        channel='feishu',
        owner_user_id='user_1',
        manager_user_id='helper_1',
        display_name='owned-by-user-1',
        credentials={'app_id': 'cli_a', 'app_secret': 'sec_a'},
    ))
    asyncio.run(store.create_binding(
        channel='weixin_clawbot',
        owner_user_id='user_2',
        manager_user_id='user_1',
        display_name='managed-by-user-1',
        credentials={},
    ))
    asyncio.run(store.create_binding(
        channel='feishu',
        owner_user_id='user_3',
        manager_user_id='helper_3',
        display_name='hidden-from-user-1',
        credentials={'app_id': 'cli_c', 'app_secret': 'sec_c'},
    ))

    user_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )
    admin_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='admin_1',
            email='admin@example.com',
            role='admin',
        ),
    )

    user_response = user_client.get('/api/channels/bindings', params={'scope': 'my'})
    admin_response = admin_client.get('/api/channels/bindings', params={'scope': 'all'})

    assert user_response.status_code == 200
    assert sorted(item['owner_user_id'] for item in user_response.json()['items']) == [
        'user_1',
        'user_2',
    ]
    assert admin_response.status_code == 200
    assert sorted(item['owner_user_id'] for item in admin_response.json()['items']) == [
        'user_1',
        'user_2',
        'user_3',
    ]


def test_owner_can_delete_collaborator_binding(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    binding = asyncio.run(store.create_binding(
        channel='weixin_clawbot',
        owner_user_id='user_1',
        manager_user_id='helper_1',
        display_name='collab-binding',
        credentials={},
        runtime_state={'status': 'pending', 'qrcode': 'qr_1'},
    ))
    stopped = {}

    async def fake_stop_runtime(binding_id):
        stopped['binding_id'] = binding_id

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.service.stop_weixin_binding_runtime',
        fake_stop_runtime,
    )

    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )

    response = client.delete(f'/api/channels/weixin-clawbot/bindings/{binding.id}')

    assert response.status_code == 200
    assert response.json() == {'binding_id': binding.id, 'deleted': True}
    assert stopped['binding_id'] == binding.id
    assert asyncio.run(store.get_binding(binding.id)) is None


def test_feishu_binding_routes_support_multiple_bindings_per_owner(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    started = []

    async def fake_start_runtime(*, binding_id, store):
        started.append(binding_id)

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.feishu.service.start_feishu_runtime',
        fake_start_runtime,
    )

    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )

    first = client.post(
        '/api/channels/feishu/bindings',
        json={
            'owner_user_id': 'user_1',
            'display_name': '市场部机器人',
            'app_id': 'cli_a',
            'app_secret': 'sec_a',
            'domain': 'feishu',
            'group_policy': 'mention',
            'streaming': True,
        },
    )
    second = client.post(
        '/api/channels/feishu/bindings',
        json={
            'owner_user_id': 'user_1',
            'display_name': '客服值班号',
            'app_id': 'cli_b',
            'app_secret': 'sec_b',
            'domain': 'feishu',
            'group_policy': 'mention',
            'streaming': True,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['id'] != second.json()['id']
    assert started == [first.json()['id'], second.json()['id']]



def test_weixin_binding_refresh_qrcode_restarts_runtime(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    weixin_client = FakeWeixinClient()
    started = []
    stopped = []

    async def fake_start_runtime(*, binding_id, store):
        started.append({'binding_id': binding_id, 'store': store})
        return None

    async def fake_stop_runtime(binding_id):
        stopped.append(binding_id)

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.service.start_weixin_binding_runtime',
        fake_start_runtime,
    )
    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.service.stop_weixin_binding_runtime',
        fake_stop_runtime,
    )

    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
        weixin_client=weixin_client,
    )

    create_response = client.post(
        '/api/channels/weixin-clawbot/bindings',
        json={
            'owner_user_id': 'user_1',
            'display_name': 'binding-a',
        },
    )
    binding_id = create_response.json()['id']
    refresh_response = client.post(
        f'/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode'
    )

    assert create_response.status_code == 200
    assert refresh_response.status_code == 200
    assert stopped == [binding_id]
    assert started == [
        {'binding_id': binding_id, 'store': store},
        {'binding_id': binding_id, 'store': store},
    ]


def test_weixin_binding_routes_create_status_and_delete(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    weixin_client = FakeWeixinClient()
    started = []
    stopped = {}

    async def fake_start_runtime(*, binding_id, store):
        started.append({'binding_id': binding_id, 'store': store})
        return None

    async def fake_stop_runtime(binding_id):
        stopped['binding_id'] = binding_id

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.service.start_weixin_binding_runtime',
        fake_start_runtime,
    )
    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.service.stop_weixin_binding_runtime',
        fake_stop_runtime,
    )

    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
        weixin_client=weixin_client,
    )

    create_response = client.post(
        '/api/channels/weixin-clawbot/bindings',
        json={
            'owner_user_id': 'user_1',
            'display_name': 'binding-a',
        },
    )
    binding_id = create_response.json()['id']
    assert create_response.status_code == 200
    assert create_response.json()['display_name'] == 'binding-a'
    assert create_response.json()['qrcode_url'] == 'https://example.test/qrcode.png'
    assert started == [{'binding_id': binding_id, 'store': store}]

    status_response = client.get(
        f'/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode/status'
    )
    delete_response = client.delete(
        f'/api/channels/weixin-clawbot/bindings/{binding_id}'
    )

    assert status_response.status_code == 200
    assert status_response.json()['status'] == 'confirmed'
    assert started[-1]['binding_id'] == binding_id
    assert started[-1]['store'] is store
    assert delete_response.status_code == 200
    assert delete_response.json() == {'binding_id': binding_id, 'deleted': True}
    assert stopped['binding_id'] == binding_id


import importlib

import pytest
from fastapi import FastAPI
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
    from deepclaw.web_backend.channels.router import create_channels_router

    app = FastAPI()
    app.include_router(
        create_channels_router(
            store=store,
            service=service,
            weixin_client=weixin_client,
        )
    )
    if actor is not None:
        app.dependency_overrides[get_current_actor] = lambda: actor
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)

def test_channels_router_is_importable_from_nested_business_api_package():
    from deepclaw.web_backend.channels.router import create_channels_router

    assert callable(create_channels_router)


def test_channels_router_assembles_domain_routers():
    from deepclaw.web_backend.channels.dingtalk.router import create_dingtalk_router
    from deepclaw.web_backend.channels.feishu.router import create_feishu_router
    from deepclaw.web_backend.channels.session_router import (
        create_channel_sessions_router,
    )
    from deepclaw.web_backend.channels.weixin_clawbot.router import (
        create_weixin_clawbot_router,
    )

    assert callable(create_channel_sessions_router)
    assert callable(create_feishu_router)
    assert callable(create_dingtalk_router)
    assert callable(create_weixin_clawbot_router)


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
    session = store.get_or_create_session(channel='feishu', channel_conversation_id='chat_a', channel_user_id='ou_1', user_id='user_1', manager_user_id='user_1')
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
    session = store.get_or_create_session(channel='feishu', channel_conversation_id='chat_a', channel_user_id='ou_1', user_id='user_1', manager_user_id='user_1')
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
    guest_session = store.get_or_create_session(
        channel='weixin_clawbot',
        channel_conversation_id='guest:chat_a',
        channel_user_id='guest:wx_1',
        user_id='guest',
        manager_user_id='guest',
    )
    user_session = store.get_or_create_session(
        channel='feishu',
        channel_conversation_id='chat_b',
        channel_user_id='ou_2',
        user_id='user_1',
        manager_user_id='user_1',
    )
    other_session = store.get_or_create_session(
        channel='feishu',
        channel_conversation_id='chat_c',
        channel_user_id='ou_3',
        user_id='user_2',
        manager_user_id='user_2',
    )

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
    first = store.get_or_create_session(
        channel='feishu',
        channel_conversation_id='chat_a',
        channel_user_id='ou_1',
        user_id='user_1',
        manager_user_id='user_1',
    )
    second = store.get_or_create_session(
        channel='weixin_clawbot',
        channel_conversation_id='guest:chat_b',
        channel_user_id='guest:wx_2',
        user_id='guest',
        manager_user_id='guest',
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
    from deepclaw.web_backend.channels.router import create_channels_router
    store = ChannelStore('sqlite:///:memory:')
    service = FakeService()
    app = FastAPI()
    app.include_router(create_channels_router(store=store, service=service))
    client = TestClient(app)
    response = client.post('/api/channels/feishu/events', json={'message_id': 'msg_1', 'channel_user_id': 'ou_1', 'channel_conversation_id': 'chat_a', 'text': 'hello'})
    assert 200 == response.status_code
    assert {'status': 'accepted'} == response.json()
    assert 1 == len(service.calls)
    assert 'feishu' == service.calls[0][0].channel


def test_feishu_binding_routes_create_and_delete_binding(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    started = []
    stopped = {}

    async def fake_start_runtime(*, binding_id, store):
        started.append({'binding_id': binding_id, 'store': store})
        return None

    async def fake_stop_runtime(binding_id):
        stopped['binding_id'] = binding_id

    monkeypatch.setattr(
        "deepclaw.web_backend.channels.feishu.router.start_feishu_runtime",
        fake_start_runtime,
    )
    monkeypatch.setattr(
        "deepclaw.web_backend.channels.feishu.router.stop_feishu_runtime",
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

    create_response = client.post(
        '/api/channels/feishu/users/user_1/binding',
        json={
            'app_id': 'cli_x',
            'app_secret': 'sec_x',
            'domain': 'feishu',
            'group_policy': 'mention',
            'streaming': True,
        },
    )
    get_response = client.get('/api/channels/feishu/users/user_1/binding')
    delete_response = client.delete('/api/channels/feishu/users/user_1/binding')

    assert 200 == create_response.status_code
    assert 200 == get_response.status_code
    assert 200 == delete_response.status_code
    assert 'cli_x' == get_response.json()['credentials']['app_id']
    assert 'mention' == get_response.json()['config']['group_policy']
    assert started[-1]['binding_id'] == get_response.json()['id']
    assert store is started[-1]['store']
    assert stopped['binding_id'] == get_response.json()['id']


def test_feishu_binding_list_respects_actor_scope():
    store = ChannelStore('sqlite:///:memory:')
    store.create_binding(
        channel='feishu',
        owner_user_id='user_1',
        manager_user_id='helper_1',
        display_name='owned-by-user-1',
        credentials={'app_id': 'cli_1', 'app_secret': 'sec_1'},
        runtime_state={'status': 'connected'},
    )
    store.create_binding(
        channel='feishu',
        owner_user_id='user_2',
        manager_user_id='user_1',
        display_name='Feishu user_2',
        credentials={'app_id': 'cli_2', 'app_secret': 'sec_2'},
        runtime_state={'status': 'connected'},
    )
    store.create_binding(
        channel='feishu',
        owner_user_id='user_3',
        manager_user_id='helper_3',
        display_name='hidden-from-user-1',
        credentials={'app_id': 'cli_c', 'app_secret': 'sec_c'},
    )

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

    user_response = user_client.get('/api/channels/feishu/users')
    admin_response = admin_client.get('/api/channels/feishu/users')

    assert 200 == user_response.status_code
    assert ['user_1', 'user_2'] == sorted(
        item['owner_user_id'] for item in user_response.json()['items']
    )
    assert 200 == admin_response.status_code
    assert ['user_1', 'user_2', 'user_3'] == sorted(
        item['owner_user_id'] for item in admin_response.json()['items']
    )

def test_weixin_clawbot_poll_accepts_text_updates():
    from deepclaw.web_backend.channels.router import create_channels_router
    store = ChannelStore('sqlite:///:memory:')
    service = FakeService()
    weixin_client = FakeWeixinClient()
    app = FastAPI()
    app.include_router(create_channels_router(store=store, service=service, weixin_client=weixin_client))
    client = TestClient(app)
    response = client.post('/api/channels/weixin-clawbot/poll', json={'bot_token': 'token_1', 'get_updates_buf': 'old_buf'})
    assert 200 == response.status_code
    assert {'status': 'accepted', 'accepted': 1, 'get_updates_buf': 'next_buf'} == response.json()
    assert 'token_1' == weixin_client.token
    assert 'old_buf' == weixin_client.get_updates_buf
    assert 1 == len(service.calls)
    assert 'weixin_clawbot' == service.calls[0][0].channel

def test_weixin_clawbot_qrcode_routes_return_link_and_status():
    from deepclaw.web_backend.channels.router import create_channels_router
    store = ChannelStore('sqlite:///:memory:')
    weixin_client = FakeWeixinClient()
    app = FastAPI()
    app.include_router(create_channels_router(store=store, weixin_client=weixin_client))
    client = TestClient(app)
    qrcode_response = client.post('/api/channels/weixin-clawbot/qrcode', json={'local_token_list': ['old_token']})
    status_response = client.get('/api/channels/weixin-clawbot/qrcode/status', params={'qrcode': 'qr-content', 'verify_code': '1234'})
    assert 200 == qrcode_response.status_code
    assert {'qrcode': 'qr-content', 'qrcode_url': 'https://example.test/qrcode.png', 'raw': {'qrcode': 'qr-content', 'qrcode_img_content': 'https://example.test/qrcode.png'}} == qrcode_response.json()
    assert ['old_token'] == weixin_client.local_token_list
    assert 200 == status_response.status_code
    assert 'confirmed' == status_response.json()['status']
    assert 'token_1' == status_response.json()['bot_token']
    assert 'qr-content' == weixin_client.qrcode
    assert '1234' == weixin_client.verify_code

def test_weixin_clawbot_user_qrcode_routes_persist_user_runtime_state(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    weixin_client = FakeWeixinClient()
    started = {}

    async def fake_start_runtime(*, state_key, store, qrcode):
        started['state_key'] = state_key
        started['store'] = store
        started['qrcode'] = qrcode
        return None
    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='manager_1',
            email='manager_1@example.com',
            role='user',
        ),
        weixin_client=weixin_client,
    )
    monkeypatch.setattr(
        "deepclaw.web_backend.channels.weixin_clawbot.router.start_weixin_clawbot_runtime",
        fake_start_runtime,
    )
    qrcode_response = client.post('/api/channels/weixin-clawbot/users/user_1/qrcode')
    status_response = client.get('/api/channels/weixin-clawbot/users/user_1/qrcode/status')
    assert 200 == qrcode_response.status_code
    assert 200 == status_response.status_code
    runtime_state = store.get_runtime_state(channel='weixin_clawbot', state_key='user:user_1')
    bindings = store.list_bindings(channel='weixin_clawbot', owner_user_id='user_1')
    assert 'user_1' == runtime_state.data['owner_user_id']
    assert 'manager_1' == runtime_state.data['manager_user_id']
    assert 'qr-content' == runtime_state.data['qrcode']
    assert 'token_1' == runtime_state.data['bot_token']
    assert 'https://node.example.test' == runtime_state.data['base_url']
    assert 1 == len(bindings)
    assert 'manager_1' == bindings[0].manager_user_id
    assert 'qr-content' == bindings[0].runtime_state['qrcode']
    assert 'token_1' == bindings[0].credentials['bot_token']
    assert 'user:user_1' == started['state_key']
    assert store is started['store']
    assert 'qr-content' == started['qrcode']

def test_weixin_clawbot_user_qrcode_timeout_returns_504():
    client = build_channels_client(
        store=ChannelStore('sqlite:///:memory:'),
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
        weixin_client=TimeoutWeixinClient(),
        raise_server_exceptions=False,
    )
    response = client.post('/api/channels/weixin-clawbot/users/user_1/qrcode')
    assert 504 == response.status_code
    assert 'Weixin ClawBot request timed out. Please try again.' == response.json()['detail']

def test_weixin_clawbot_user_status_uses_local_runtime_when_connected():
    store = ChannelStore('sqlite:///:memory:')
    store.upsert_runtime_state(channel='weixin_clawbot', state_key='user:user_1', data={'owner_user_id': 'user_1', 'manager_user_id': 'user_1', 'qrcode': 'qr_1', 'qrcode_url': 'https://liteapp.weixin.qq.com/q/test?qrcode=qr_1', 'bot_token': 'token_1', 'base_url': 'https://node.example.test'})
    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
        weixin_client=TimeoutWeixinClient(),
        raise_server_exceptions=False,
    )
    response = client.get('/api/channels/weixin-clawbot/users/user_1/qrcode/status')
    assert 200 == response.status_code
    assert 'confirmed' == response.json()['status']
    assert 'token_1' == response.json()['bot_token']
    assert 'https://node.example.test' == response.json()['base_url']

def test_weixin_clawbot_user_management_lists_and_deletes_bound_users(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    store.upsert_runtime_state(channel='weixin_clawbot', state_key='user:user_1', data={'owner_user_id': 'user_1', 'manager_user_id': 'user_1', 'bot_token': 'token_1', 'qrcode': 'qr_1', 'qrcode_url': 'https://example.test/qr_1.png', 'base_url': 'https://node.example.test'})
    store.upsert_runtime_state(channel='weixin_clawbot', state_key='default', data={'bot_token': 'legacy_token'})
    stopped = {}

    async def fake_stop_runtime(state_key):
        stopped['state_key'] = state_key
    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )
    monkeypatch.setattr(
        "deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_clawbot_runtime",
        fake_stop_runtime,
    )
    list_response = client.get('/api/channels/weixin-clawbot/users')
    delete_response = client.delete('/api/channels/weixin-clawbot/users/user_1')
    assert 200 == list_response.status_code
    assert 1 == list_response.json()['total']
    assert 'user_1' == list_response.json()['items'][0]['user_id']
    assert list_response.json()['items'][0]['connected']
    assert 'token...n_1' == list_response.json()['items'][0]['bot_token']
    assert 200 == delete_response.status_code
    assert {'user_id': 'user_1', 'deleted': True} == delete_response.json()
    assert 'user:user_1' == stopped['state_key']
    assert store.get_runtime_state(channel='weixin_clawbot', state_key='user:user_1') is None


def test_weixin_clawbot_user_management_respects_guest_and_user_scope(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    store.upsert_runtime_state(
        channel='weixin_clawbot',
        state_key='user:guest_demo_1',
        data={
            'owner_user_id': 'guest_demo_1',
            'manager_user_id': 'guest',
            'bot_token': 'token_guest_1',
        },
    )
    store.upsert_runtime_state(
        channel='weixin_clawbot',
        state_key='user:guest_demo_2',
        data={
            'owner_user_id': 'guest_demo_2',
            'manager_user_id': 'guest',
            'bot_token': 'token_guest_2',
        },
    )
    store.upsert_runtime_state(
        channel='weixin_clawbot',
        state_key='user:user_bound_1',
        data={
            'owner_user_id': 'user_bound_1',
            'manager_user_id': 'user_1',
            'bot_token': 'token_user_1',
        },
    )
    stopped = {'count': 0}

    async def fake_stop_runtime(state_key):
        stopped['count'] += 1
        stopped['state_key'] = state_key

    monkeypatch.setattr(
        "deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_clawbot_runtime",
        fake_stop_runtime,
    )

    guest_client = build_channels_client(
        store=store,
        actor=CurrentActor(is_guest=True, user_id=None, email=None, role='guest'),
    )
    guest_list = guest_client.get('/api/channels/weixin-clawbot/users')
    guest_delete_other = guest_client.delete('/api/channels/weixin-clawbot/users/user_bound_1')

    assert 200 == guest_list.status_code
    assert 2 == guest_list.json()['total']
    assert ['guest_demo_1', 'guest_demo_2'] == [
        item['user_id'] for item in guest_list.json()['items']
    ]
    assert 404 == guest_delete_other.status_code
    assert 0 == stopped['count']

    user_client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_1',
            email='user_1@example.com',
            role='user',
        ),
    )
    user_list = user_client.get('/api/channels/weixin-clawbot/users')
    user_delete_other = user_client.delete('/api/channels/weixin-clawbot/users/guest_demo_1')

    assert 200 == user_list.status_code
    assert 1 == user_list.json()['total']
    assert 'user_bound_1' == user_list.json()['items'][0]['user_id']
    assert 404 == user_delete_other.status_code
    assert 0 == stopped['count']


def test_weixin_clawbot_user_management_allows_admin_override(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    store.upsert_runtime_state(
        channel='weixin_clawbot',
        state_key='user:user_bound_1',
        data={
            'owner_user_id': 'user_bound_1',
            'manager_user_id': 'user_1',
            'bot_token': 'token_user_1',
        },
    )
    store.upsert_runtime_state(
        channel='weixin_clawbot',
        state_key='user:guest_demo_1',
        data={
            'owner_user_id': 'guest_demo_1',
            'manager_user_id': 'guest',
            'bot_token': 'token_guest_1',
        },
    )
    stopped = {}

    async def fake_stop_runtime(state_key):
        stopped['state_key'] = state_key

    monkeypatch.setattr(
        "deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_clawbot_runtime",
        fake_stop_runtime,
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
    list_response = admin_client.get('/api/channels/weixin-clawbot/users')
    delete_response = admin_client.delete('/api/channels/weixin-clawbot/users/user_bound_1')

    assert 200 == list_response.status_code
    assert 2 == list_response.json()['total']
    assert ['guest_demo_1', 'user_bound_1'] == sorted(
        item['user_id'] for item in list_response.json()['items']
    )
    assert 200 == delete_response.status_code
    assert {'user_id': 'user_bound_1', 'deleted': True} == delete_response.json()
    assert 'user:user_bound_1' == stopped['state_key']


def test_weixin_clawbot_user_status_hides_other_manager_runtime():
    store = ChannelStore('sqlite:///:memory:')
    store.upsert_runtime_state(
        channel='weixin_clawbot',
        state_key='user:user_bound_1',
        data={
            'owner_user_id': 'user_bound_1',
            'manager_user_id': 'user_1',
            'qrcode': 'qr_1',
            'bot_token': 'token_1',
            'base_url': 'https://node.example.test',
        },
    )
    client = build_channels_client(
        store=store,
        actor=CurrentActor(
            is_guest=False,
            user_id='user_2',
            email='user_2@example.com',
            role='user',
        ),
        weixin_client=TimeoutWeixinClient(),
        raise_server_exceptions=False,
    )

    response = client.get('/api/channels/weixin-clawbot/users/user_bound_1/qrcode/status')

    assert 404 == response.status_code


def _legacy_test_binding_list_route_respects_my_and_all_scope():
    store = ChannelStore('sqlite:///:memory:')
    store.create_binding(
        channel='feishu',
        owner_user_id='user_1',
        manager_user_id='helper_1',
        display_name='市场部机器人',
        credentials={'app_id': 'cli_a', 'app_secret': 'sec_a'},
    )
    store.create_binding(
        channel='weixin_clawbot',
        owner_user_id='user_2',
        manager_user_id='user_2',
        display_name='李四代绑号',
        credentials={},
    )

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

    assert [item['display_name'] for item in user_response.json()['items']] == ['市场部机器人']
    assert sorted(item['owner_user_id'] for item in user_response.json()['items']) == ['user_1', 'user_2']
    assert sorted(item['owner_user_id'] for item in admin_response.json()['items']) == ['user_1', 'user_2', 'user_3']


def test_binding_list_route_includes_owner_and_manager_participants():
    store = ChannelStore('sqlite:///:memory:')
    store.create_binding(
        channel='feishu',
        owner_user_id='user_1',
        manager_user_id='helper_1',
        display_name='owned-by-user-1',
        credentials={'app_id': 'cli_a', 'app_secret': 'sec_a'},
    )
    store.create_binding(
        channel='weixin_clawbot',
        owner_user_id='user_2',
        manager_user_id='user_1',
        display_name='managed-by-user-1',
        credentials={},
    )
    store.create_binding(
        channel='feishu',
        owner_user_id='user_3',
        manager_user_id='helper_3',
        display_name='hidden-from-user-1',
        credentials={'app_id': 'cli_c', 'app_secret': 'sec_c'},
    )

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
    binding = store.create_binding(
        channel='weixin_clawbot',
        owner_user_id='user_1',
        manager_user_id='helper_1',
        display_name='collab-binding',
        credentials={},
        runtime_state={'status': 'pending', 'qrcode': 'qr_1'},
    )
    stopped = {}

    async def fake_stop_runtime(binding_id):
        stopped['binding_id'] = binding_id

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_binding_runtime',
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
    assert store.get_binding(binding.id) is None


def test_feishu_binding_routes_support_multiple_bindings_per_owner(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    started = []

    async def fake_start_runtime(*, binding_id, store):
        started.append(binding_id)

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.feishu.router.start_feishu_runtime',
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


def legacy_weixin_binding_routes_create_status_and_delete(monkeypatch):
    store = ChannelStore('sqlite:///:memory:')
    weixin_client = FakeWeixinClient()
    started = {}
    stopped = {}

    async def fake_start_runtime(*, binding_id, store):
        started['binding_id'] = binding_id
        started['store'] = store
        return None

    async def fake_stop_runtime(binding_id):
        stopped['binding_id'] = binding_id

    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.router.start_weixin_binding_runtime',
        fake_start_runtime,
    )
    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_binding_runtime',
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
            'display_name': '张三主号',
        },
    )
    binding_id = create_response.json()['id']
    assert create_response.status_code == 200
    assert create_response.json()['display_name'] == '寮犱笁涓诲彿'
    assert create_response.json()['qrcode_url'] == 'https://example.test/qrcode.png'
    assert started == [{'binding_id': binding_id, 'store': store}]
    status_response = client.get(
        f'/api/channels/weixin-clawbot/bindings/{binding_id}/qrcode/status'
    )
    delete_response = client.delete(
        f'/api/channels/weixin-clawbot/bindings/{binding_id}'
    )

    assert create_response.status_code == 200
    assert create_response.json()['display_name'] == '张三主号'
    assert create_response.json()['qrcode_url'] == 'https://example.test/qrcode.png'
    assert status_response.status_code == 200
    assert status_response.json()['status'] == 'confirmed'
    assert started[-1]['binding_id'] == binding_id
    assert started[-1]['store'] is store
    assert delete_response.status_code == 200
    assert delete_response.json() == {'binding_id': binding_id, 'deleted': True}
    assert stopped['binding_id'] == binding_id


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
        'deepclaw.web_backend.channels.weixin_clawbot.router.start_weixin_binding_runtime',
        fake_start_runtime,
    )
    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_binding_runtime',
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
        'deepclaw.web_backend.channels.weixin_clawbot.router.start_weixin_binding_runtime',
        fake_start_runtime,
    )
    monkeypatch.setattr(
        'deepclaw.web_backend.channels.weixin_clawbot.router.stop_weixin_binding_runtime',
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


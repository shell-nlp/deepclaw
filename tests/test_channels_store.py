import unittest


class ChannelStoreTest(unittest.TestCase):
    def setUp(self):
        self.db_url = "sqlite:///:memory:"

    def test_get_or_create_user_reuses_channel_user_mapping(self):
        from langchain_api.channels.store import ChannelStore

        store = ChannelStore(self.db_url)

        first = store.get_or_create_user(
            channel="feishu",
            channel_user_id="ou_1",
            display_name="Alice",
        )
        second = store.get_or_create_user(
            channel="feishu",
            channel_user_id="ou_1",
            display_name="Alice Renamed",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.user_id, second.user_id)
        self.assertEqual("Alice", second.display_name)

    def test_get_or_create_session_reuses_conversation_user_mapping(self):
        from langchain_api.channels.store import ChannelStore

        store = ChannelStore(self.db_url)
        user = store.get_or_create_user(
            channel="feishu",
            channel_user_id="ou_1",
            user_id="user_1",
        )

        first = store.get_or_create_session(
            channel="feishu",
            channel_conversation_id="chat_a",
            channel_user_id="ou_1",
            user_id=user.user_id,
        )
        second = store.get_or_create_session(
            channel="feishu",
            channel_conversation_id="chat_a",
            channel_user_id="ou_1",
            user_id=user.user_id,
            reply_mode="streaming",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual("final", second.reply_mode)

    def test_update_session_reply_mode_validates_values(self):
        from langchain_api.channels.store import ChannelStore

        store = ChannelStore(self.db_url)
        session = store.get_or_create_session(
            channel="dingtalk",
            channel_conversation_id="cid_1",
            channel_user_id="ding_user_1",
            user_id="user_1",
        )

        updated = store.update_session_reply_mode(session.session_id, "streaming")
        self.assertEqual("streaming", updated.reply_mode)

        with self.assertRaises(ValueError):
            store.update_session_reply_mode(session.session_id, "verbose")

    def test_message_record_uses_channel_message_as_logical_key(self):
        from langchain_api.channels.models import ChannelMessage
        from langchain_api.channels.store import ChannelStore

        store = ChannelStore(self.db_url)
        message = ChannelMessage(
            channel="feishu",
            message_id="msg_1",
            channel_user_id="ou_1",
            channel_conversation_id="chat_a",
            text="hello",
        )

        first = store.get_or_create_message_record(message)
        second = store.get_or_create_message_record(message)
        done = store.mark_message_status("feishu", "msg_1", "done")

        self.assertEqual(first.id, second.id)
        self.assertEqual("received", second.status)
        self.assertEqual("done", done.status)


if __name__ == "__main__":
    unittest.main()

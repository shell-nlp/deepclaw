import asyncio
import json

import pytest

from deepclaw import model_config
from deepclaw.web_backend.model_store import ModelCatalogChangedError, ModelCatalogStore


def test_legacy_model_config_migrates_with_stable_ids(monkeypatch, tmp_path):
    """验证旧版单模型配置迁移后 ID 稳定，避免按 ID 寻址的接口找不到模型。"""

    config_path = tmp_path / "model_config.json"
    config_path.write_text(
        json.dumps(
            {
                "OPENAI_API_BASE": "https://legacy.example.com/v1",
                "OPENAI_API_KEY": "sk-legacy-123456789",
                "CHAT_MODEL_NAME": "legacy-chat",
                "EMBEDDING_MODEL_NAME": "legacy-emb",
                "MODEL_CONTEXT_WINDOW": 32000,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_config, "MODEL_CONFIG_PATH", config_path)
    monkeypatch.setattr("deepclaw.web_backend.model_store.apply_active_model_config", lambda state: None)
    db_url = f"sqlite:///{(tmp_path / 'deepclaw.db').as_posix()}"
    async def verify_migration():
        """验证数据库重开和并发写入后的目录状态。

        Args:
            无。
        """
        first_store = ModelCatalogStore(db_url)
        second_store = ModelCatalogStore(db_url)
        try:
            first = await first_store.load()
            assert not config_path.exists()
            second = await second_store.load()
            first["models"][0]["reasoning_efforts"] = ["high", "max"]
            await first_store.save(first)
            with pytest.raises(ModelCatalogChangedError):
                await second_store.save(second)
            assert (await second_store.load())["models"][0]["reasoning_efforts"] == ["high", "max"]
        finally:
            await first_store.engine.dispose()
            await second_store.engine.dispose()

        return first, second

    first, second = asyncio.run(verify_migration())

    assert [model["id"] for model in first["models"]] == [model["id"] for model in second["models"]]
    assert {model["type"] for model in first["models"]} == {"chat", "embedding"}
    assert first["active_chat_model_id"] == next(
        model["id"] for model in first["models"] if model["type"] == "chat"
    )

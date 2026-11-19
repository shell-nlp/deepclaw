import json

from deepclaw import model_config


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
    monkeypatch.setattr(model_config, "HOME_PATH", tmp_path)

    first = model_config.load_model_state()
    second = model_config.load_model_state()

    assert [model["id"] for model in first["models"]] == [model["id"] for model in second["models"]]
    assert {model["type"] for model in first["models"]} == {"chat", "embedding"}
    assert first["active_chat_model_id"] == next(
        model["id"] for model in first["models"] if model["type"] == "chat"
    )
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(persisted.get("models"), list)

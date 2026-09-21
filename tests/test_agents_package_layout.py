import importlib


def test_general_agent_modules_are_importable_from_agents_package():
    agent_module = importlib.import_module("deepclaw.agents.general.agent")
    state_module = importlib.import_module("deepclaw.agents.general.state")
    utils_module = importlib.import_module("deepclaw.agents.general.utils")

    assert hasattr(agent_module, "GeneralAgent")
    assert hasattr(state_module, "StateSchema")
    assert hasattr(utils_module, "copy_skills_to_store")


def test_rag_agent_modules_are_importable_from_agents_package():
    agent_module = importlib.import_module("deepclaw.agents.rag.agent")
    state_module = importlib.import_module("deepclaw.agents.rag.state")

    assert hasattr(agent_module, "RagAgent")
    assert hasattr(state_module, "StateSchema")


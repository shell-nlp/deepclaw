import importlib


def test_general_agent_modules_are_importable_from_agents_package():
    agent_module = importlib.import_module("deepclaw.agents.general.agent")
    context_module = importlib.import_module("deepclaw.agents.general.context")
    state_module = importlib.import_module("deepclaw.agents.general.state")
    utils_module = importlib.import_module("deepclaw.agents.general.utils")

    assert hasattr(agent_module, "Agent")
    assert hasattr(context_module, "AgentContext")
    assert hasattr(state_module, "StateSchema")
    assert hasattr(utils_module, "copy_skills_to_store")


def test_rag_agent_modules_are_importable_from_agents_package():
    agent_module = importlib.import_module("deepclaw.agents.rag.agent")
    context_module = importlib.import_module("deepclaw.agents.rag.context")
    state_module = importlib.import_module("deepclaw.agents.rag.state")

    assert hasattr(agent_module, "create_rag_agent")
    assert hasattr(context_module, "AgentContext")
    assert hasattr(state_module, "StateSchema")


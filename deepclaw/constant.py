from pathlib import Path

root_dir = Path(__file__).parent.parent

# 宿主侧路径（Windows / Linux / macOS 通用，由 pathlib.Path 自动处理分隔符）
home_path = root_dir / ".deepclaw"
workspace_path = home_path / "workspace"

# 沙箱容器内路径（OpenSandbox 是 Linux 容器，路径必须保持 POSIX 风格，
# 千万不要换成 host 路径，否则容器内部访问不到）。
SANDBOX_SHARED_WORKSPACE = "/shared_workspace"
SANDBOX_HOME = "/.deepclaw"
SANDBOX_USER_WORKSPACE = f"{SANDBOX_HOME}/workspace"
SANDBOX_USER_SKILLS = f"{SANDBOX_USER_WORKSPACE}/skills"
SANDBOX_USER_AGENTS = f"{SANDBOX_USER_WORKSPACE}/AGENTS.md"
SANDBOX_SHARED_SKILLS = f"{SANDBOX_SHARED_WORKSPACE}/skills"
SANDBOX_SHARED_AGENTS = f"{SANDBOX_SHARED_WORKSPACE}/AGENTS.md"

# Agent 抽象的虚拟路径，由 StoreBackend 路由，与宿主 OS 无关
AGENT_VIRTUAL_MEMORIES = "/memories"
AGENT_VIRTUAL_PREFERENCES = f"{AGENT_VIRTUAL_MEMORIES}/preferences.md"


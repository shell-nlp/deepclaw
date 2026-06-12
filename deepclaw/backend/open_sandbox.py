import hashlib
import re
import tomllib
from datetime import timedelta
from pathlib import Path

from deepagents.backends.sandbox import (
    BaseSandbox,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    WriteResult,
)
from langgraph.runtime import get_runtime
from loguru import logger
from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync
from opensandbox.models import WriteEntry
from opensandbox.models.execd import (
    RunCommandOpts,
)
from opensandbox.models.sandboxes import Host, Volume

from deepclaw.constant import root_dir, workspace_path
from deepclaw.settings import settings

with open(root_dir / ".sandbox.toml", "rb") as f:
    config = tomllib.load(f)

DOMAIN = config["server"]["host"] + ":" + str(config["server"]["port"])

user_workspace_path = root_dir / "user_workspace"

_SANDBOX_NAME_MAX_LENGTH = 63
_SANDBOX_NAME_HASH_LENGTH = 8


def build_sandbox_volume_name(prefix: str, user_id: str) -> str:
    """构造符合资源命名约束的 volume 名称，并通过哈希避免不同用户清洗后重名。"""
    normalized_prefix = re.sub(r"[^a-z0-9-]+", "-", prefix.lower()).strip("-") or "sandbox"
    normalized_user = re.sub(r"[^a-z0-9-]+", "-", user_id.lower()).strip("-") or "user"
    digest = hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:_SANDBOX_NAME_HASH_LENGTH]

    available = _SANDBOX_NAME_MAX_LENGTH - len(digest) - 2
    prefix_max_length = max(1, available - 2)
    trimmed_prefix = normalized_prefix[:prefix_max_length].rstrip("-") or "sandbox"
    user_max_length = max(1, available - len(trimmed_prefix) - 1)
    trimmed_user = normalized_user[:user_max_length].rstrip("-") or "user"
    return f"{trimmed_prefix}-{trimmed_user}-{digest}"


class OpenSandbox(BaseSandbox):
    """
    OpenSandbox backend for DeepAgents.
    """

    def __init__(
        self,
        env: dict[str, str] = {"PYTHON_VERSION": "3.11"},
        timeout: int = 60 * 5,
        volumes: list[Volume] | None = None,
    ):
        self.env = env
        self.timeout = timeout
        self.volumes = volumes
        # 1. 配置连接信息
        self.config = ConnectionConfigSync(domain=DOMAIN)

    def get_user_workspace_path(self, user_id: str) -> str:
        """为用户提前创建工作空间"""
        new_workspace_path = Path(f"{user_workspace_path}/{user_id}/.deepclaw")
        new_workspace_path.mkdir(parents=True, exist_ok=True)
        # conversation_history
        conversation_history = new_workspace_path / "conversation_history"
        conversation_history.mkdir(parents=True, exist_ok=True)
        #  skill 保存目录
        new_skills_path = new_workspace_path / "workspace" / "skills"
        new_skills_path.mkdir(parents=True, exist_ok=True)
        return str(new_workspace_path)

    def create_sandbox(self, user_id) -> SandboxSync:
        """创建用户沙箱 skills 私有,没有公共沙箱"""
        _user_workspace_path = self.get_user_workspace_path(user_id)
        return SandboxSync.create(
            image=settings.OPEN_SANDBOX_CODE_INTERPRETER_IMAGE,
            entrypoint=["/opt/code-interpreter/code-interpreter.sh"],
            env=self.env,
            timeout=timedelta(seconds=self.timeout),
            connection_config=self.config,
            volumes=[
                # 私有 skills 目录
                Volume(
                    name=build_sandbox_volume_name("deepclaw", user_id),
                    host=Host(path=_user_workspace_path),
                    mount_path="/.deepclaw",
                ),
                Volume(
                    name=build_sandbox_volume_name("deepclaw-conversation-history", user_id),
                    host=Host(path=_user_workspace_path + "/conversation_history"),
                    mount_path="/conversation_history",
                ),
            ],
        )

    def create_sandbox_v2(self, user_id) -> SandboxSync:
        """创建用户沙箱 skills 共享 + skills 私有"""
        _user_workspace_path = self.get_user_workspace_path(user_id)
        return SandboxSync.create(
            image=settings.OPEN_SANDBOX_CODE_INTERPRETER_IMAGE,
            entrypoint=["/opt/code-interpreter/code-interpreter.sh"],
            env=self.env,
            timeout=timedelta(seconds=self.timeout),
            connection_config=self.config,
            volumes=[
                # 私有 skills 目录
                Volume(
                    name=build_sandbox_volume_name("deepclaw", user_id),
                    host=Host(path=_user_workspace_path),
                    mount_path="/.deepclaw",
                ),
                Volume(
                    name=build_sandbox_volume_name("deepclaw-conversation-history", user_id),
                    host=Host(path=_user_workspace_path + "/conversation_history"),
                    mount_path="/conversation_history",
                ),
                # 公共 skills 目录
                Volume(
                    name=build_sandbox_volume_name("deepclaw-skills", user_id),
                    host=Host(path=str(workspace_path / "skills")),
                    mount_path="/workspace/skills",
                ),
            ],
        )

    def connect_sandbox(self, sandbox_id: str) -> SandboxSync:
        return SandboxSync.connect(sandbox_id=sandbox_id, connection_config=self.config)

    def get_sandbox(self) -> SandboxSync:
        runtime = get_runtime()
        user_id = runtime.context.user_id
        user_store_item = runtime.store.get((f"user_{user_id}",), "sandbox_id")
        if user_store_item:
            logger.debug(f"得到用户:{user_id} 已存在的沙箱ID: {user_store_item.value['sandbox_id']}")
            try:
                return self.connect_sandbox(user_store_item.value["sandbox_id"])
            except Exception as e:
                logger.warning(f"连接已有沙箱失败({e})，将为用户: {user_id} 创建新沙箱")
                runtime.store.delete((f"user_{user_id}",), "sandbox_id")

        sandbox = self.create_sandbox_v2(user_id)
        sandbox_id = sandbox.id
        runtime.store.put((f"user_{user_id}",), "sandbox_id", {"sandbox_id": sandbox_id})
        logger.debug(f"为用户: {user_id} 创建新沙箱, 沙箱 ID 为 {sandbox_id}")
        return sandbox

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        sandbox = self.get_sandbox()
        with sandbox:
            exit_code = 0
            if timeout is None:
                timeout = 60 * 10
            try:
                # TODO 内部调用 http 沙盒的接口的超时，官方未传递 timeout 参数
                execution = sandbox.commands.run(
                    command,
                    opts=RunCommandOpts(timeout=timedelta(seconds=timeout or self.timeout)),
                )
                output = str(execution)
                # output = execution.logs.stdout
                # if output:
                #     output = "\n".join([msg.text for msg in output])
                # else:
                #     output = ""
            except Exception as e:
                output = str(e)
                exit_code = 1
            # sandbox.kill()
            return ExecuteResponse(
                output=output,
                exit_code=exit_code,
                truncated=False,
            )

    def write(self, file_path: str, content: str) -> WriteResult:
        sandbox = self.get_sandbox()
        sandbox.files.write_file(path=file_path, data=content)
        return WriteResult(path=file_path)

    def ls(self, path: str):
        return super().ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return super().read(file_path, offset, limit)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        return super().edit(file_path, old_string, new_string, replace_all)

    def glob(self, pattern: str, path: str | None = None):
        return super().glob(pattern, path)

    def grep(self, pattern: str, path: str | None = None):
        return super().grep(pattern, path)

    @property
    def id(self) -> str:
        return "open_sandbox"

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files to the filesystem.

        Args:
            files: List of (path, content) tuples where content is bytes.

        Returns:
            List of FileUploadResponse objects, one per input file.
            Response order matches input order.
        """
        sandbox = self.get_sandbox()
        responses: list[FileUploadResponse] = []
        write_entries = []

        for path, content in files:
            write_entries.append(WriteEntry(path=path, data=content, mode=644))

        try:
            sandbox.files.write_files(write_entries)
            for path, _ in files:
                responses.append(FileUploadResponse(path=path, error=None))
        except Exception:
            for path, content in files:
                try:
                    sandbox.files.write_file(path=path, data=content)
                    responses.append(FileUploadResponse(path=path, error=None))
                except Exception:
                    responses.append(FileUploadResponse(path=path, error="unknown_error"))

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files from the filesystem.

        Args:
            paths: List of file paths to download.

        Returns:
            List of FileDownloadResponse objects, one per input path.
        """
        # TODO 上传和下载的异常处理存在问题，暂未处理
        sandbox = self.get_sandbox()
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                content = sandbox.files.read_bytes(path)
                responses.append(FileDownloadResponse(path=path, content=content, error=None))
            except Exception:
                responses.append(FileDownloadResponse(path=path, content=None, error="unknown_error"))

        return responses


if __name__ == "__main__":
    # docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.1.0 && docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/execd:v1.0.18 && docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/egress:v1.0.13
    # opensandbox-server --config .sandbox.toml
    volumes = [
        Volume(
            name="workspace-root",
            host=Host(path="/home/dev/liuyu/project/langchain-api"),
            mount_path="/workspace2",
        )
    ]
    # volumes = None
    sandbox = OpenSandbox(volumes=volumes)
    # value = sandbox.execute("env")

    value = sandbox.write("/workspace/script.py", "print('Hello OpenSandbox!')")
    value = sandbox.read("script.py")
    # sandbox.sandbox.kill()
    print(value)

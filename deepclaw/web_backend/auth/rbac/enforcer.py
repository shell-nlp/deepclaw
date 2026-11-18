import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import casbin
from loguru import logger

from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor


DEFAULT_MODEL_FILE = "rbac_model.conf"
DEFAULT_POLICY_FILE = "rbac_policy.csv"
POLICY_SECTION = "rbac_policy"

_enforcer: casbin.Enforcer | None = None
_lock = threading.Lock()


@dataclass(slots=True)
class RbacSubject:
    """参与授权判断的主体属性。

    Args:
        uid: 主体用户 ID，游客为 guest。
        role: 主体角色，与策略中的角色名对应。
        is_admin: 是否为管理员；为真时跳过资源归属限制。
    """

    uid: str
    role: str
    is_admin: bool


@dataclass(slots=True)
class RbacResource:
    """参与授权判断的资源属性。

    Args:
        path: 资源路径，按策略中的 keyMatch 规则匹配。
        owner: 资源归属用户 ID；无归属资源传空字符串。
    """

    path: str
    owner: str = ""
    args: dict[str, str] = field(default_factory=dict)


def resolve_rbac_paths() -> tuple[Path, Path]:
    """解析模型与策略文件路径。

    未配置 RBAC_MODEL_PATH / RBAC_POLICY_PATH 时使用包内默认策略；
    配置时必须两者同时提供，避免只替换其中一半导致策略失效。

    Returns:
        tuple[Path, Path]: 模型文件路径与策略文件路径。

    Raises:
        RuntimeError: 只配置了其中一个环境变量时抛出。
    """

    configured_model = settings.RBAC_MODEL_PATH.strip()
    configured_policy = settings.RBAC_POLICY_PATH.strip()
    if configured_model or configured_policy:
        if not (configured_model and configured_policy):
            raise RuntimeError("RBAC_MODEL_PATH 和 RBAC_POLICY_PATH 必须同时配置。")
        return Path(configured_model).resolve(), Path(configured_policy).resolve()

    package_dir = Path(__file__).resolve().parent
    model_path = package_dir / DEFAULT_MODEL_FILE
    policy_path = package_dir / DEFAULT_POLICY_FILE
    # 允许把策略放在项目 data 目录，运维改策略后重启即可生效。
    project_root = package_dir.parents[3]
    for candidate_model, candidate_policy in (
        (project_root / "data" / DEFAULT_MODEL_FILE, project_root / "data" / DEFAULT_POLICY_FILE),
    ):
        if candidate_model.is_file() and candidate_policy.is_file():
            return candidate_model, candidate_policy
    return model_path, policy_path


def _build_base_model() -> casbin.model.Model:
    """加载 Casbin 模型定义，不绑定任何策略来源。

    Returns:
        casbin.model.Model: 已加载模型结构的空模型。

    Raises:
        RuntimeError: 模型文件缺失或解析失败时抛出。
    """
    model_path, _ = resolve_rbac_paths()
    if not model_path.is_file():
        raise RuntimeError(f"RBAC 模型文件不存在: {model_path}")
    try:
        model = casbin.model.Model()
        model.load_model(str(model_path))
    except Exception as exc:  # noqa: BLE001 - 启动阶段需要显式失败
        raise RuntimeError(f"RBAC 模型文件解析失败: {model_path}") from exc
    return model


def _apply_file_policies(model: casbin.model.Model) -> None:
    """把策略文件内容装载到模型。

    Args:
        model: Casbin 模型对象。

    Raises:
        RuntimeError: 策略文件缺失或解析失败时抛出。
    """
    _, policy_path = resolve_rbac_paths()
    if not policy_path.is_file():
        raise RuntimeError(f"RBAC 策略文件不存在: {policy_path}")
    try:
        casbin.persist.FileAdapter(str(policy_path)).load_policy(model)
    except Exception as exc:  # noqa: BLE001 - 启动阶段需要显式失败
        raise RuntimeError(f"RBAC 策略文件解析失败: {policy_path}") from exc


def load_page_policies(model: casbin.model.Model) -> None:
    """把数据库中的全部策略写入模型。

    Args:
        model: Casbin 模型对象。
    """
    from deepclaw.web_backend.auth.rbac.store import run_store_sync

    store = get_policy_store()
    for rule in run_store_sync(store.list_policies()):
        casbin.persist.load_policy_line(
            ",".join(("p", rule.subject, rule.path, rule.action)),
            model,
        )
    for rule in run_store_sync(store.list_roles()):
        casbin.persist.load_policy_line(",".join(("g", rule.child, rule.parent)), model)


def get_policy_store():
    """返回策略存储实例。

    Returns:
        RbacPolicyStore: 进程内共享的策略存储。
    """
    from deepclaw.web_backend.auth.rbac.store import get_rbac_policy_store

    return get_rbac_policy_store()


class _MemoryPolicyAdapter(casbin.persist.Adapter):
    """把已装载到模型的策略再回放给 Enforcer，保证角色链接被正确建立。

    Args:
        model: 已装载全部策略的模型。
    """

    def __init__(self, model: casbin.model.Model) -> None:
        self._model = model

    def load_policy(self, model) -> None:
        """把源模型中的策略行复制到目标模型。

        Args:
            model: Casbin 构造过程中传入的模型。
        """
        for ptype, policy in self._model["p"].items():
            for rule in policy.policy:
                casbin.persist.load_policy_line(",".join((ptype, *rule)), model)
        for ptype, policy in self._model["g"].items():
            for rule in policy.policy:
                casbin.persist.load_policy_line(",".join((ptype, *rule)), model)

    def save_policy(self, model) -> bool:
        """本适配器只读，不支持保存。

        Args:
            model: Casbin 模型对象。

        Returns:
            bool: 始终返回 False。
        """
        return False


def _build_enforcer() -> casbin.Enforcer:
    """按配置构建内存授权引擎。

    数据库模式先从数据库读取策略，失败时回退到策略文件；
    非数据库模式直接读取策略文件。引擎本身不挂持久化 adapter，
    策略变更通过 reload_enforcer() 显式重建。

    Returns:
        casbin.Enforcer: 已装载策略的内存授权引擎。

    Raises:
        RuntimeError: 数据库与文件都无法加载时抛出。
    """
    model = _build_base_model()
    if settings.RBAC_STORE_ENABLED:
        try:
            load_page_policies(model)
        except Exception as exc:  # noqa: BLE001 - 回退到文件策略
            logger.warning("RBAC 数据库策略不可用，回退到策略文件: {}", exc)
            model = _build_base_model()
            _apply_file_policies(model)
    else:
        _apply_file_policies(model)
    # 通过 adapter 构造，Enforcer 会重建角色链接，g 规则才会参与匹配。
    enforcer = casbin.Enforcer(model, _MemoryPolicyAdapter(model))
    enforcer.enable_log = False
    return enforcer


def get_enforcer() -> casbin.Enforcer:
    """获取进程级 Casbin 授权引擎。

    首次调用时按配置从数据库或策略文件装载策略并缓存；
    策略变更后调用 reload_enforcer() 才会重建。

    Returns:
        casbin.Enforcer: 已完成策略装载的授权引擎。

    Raises:
        RuntimeError: 策略无法装载时抛出。
    """
    global _enforcer
    if _enforcer is not None:
        return _enforcer
    with _lock:
        if _enforcer is None:
            enforcer = _build_enforcer()
            _enforcer = enforcer
            logger.info(
                "Casbin 授权策略已加载: store={} roles={} rules={}",
                settings.RBAC_STORE_ENABLED,
                sorted(enforcer.get_all_roles()),
                len(enforcer.get_policy()),
            )
    return _enforcer


def reload_enforcer() -> casbin.Enforcer:
    """丢弃已加载的授权引擎，下次调用时重新读取数据库或策略文件。

    Returns:
        casbin.Enforcer: 重新加载后的授权引擎。
    """
    global _enforcer
    with _lock:
        _enforcer = None
    return get_enforcer()


def subject_from_actor(actor: CurrentActor) -> RbacSubject:
    """把当前鉴权主体转换为 Casbin 主体属性。

    Args:
        actor: 当前请求的鉴权主体。

    Returns:
        RbacSubject: 供策略匹配使用的主体属性。
    """
    if actor.is_guest:
        return RbacSubject(uid="guest", role="guest", is_admin=False)
    return RbacSubject(
        uid=actor.user_id or "guest",
        role=actor.role,
        is_admin=actor.role == "admin",
    )


def is_allowed(
    actor: CurrentActor,
    *,
    path: str,
    action: str,
    owner: str | None = None,
    args: dict[str, str] | None = None,
) -> bool:
    """判断主体能否对指定资源执行动作。

    Args:
        actor: 当前鉴权主体。
        path: 资源路径，按策略规则匹配。
        action: 动作名称，例如 read 或 write。
        owner: 资源归属用户 ID；为空表示无归属。
        args: 资源额外属性。

    Returns:
        bool: 策略允许时返回真。
    """
    subject = subject_from_actor(actor)
    resource = RbacResource(path=path, owner=owner or "", args=args or {})
    try:
        return bool(get_enforcer().enforce(subject, resource, action))
    except casbin.exceptions.RBACError:
        return False


def describe_policies() -> str:
    """返回当前策略摘要，用于启动日志和排查。

    Returns:
        str: 策略与角色关系的 JSON 文本。
    """
    enforcer = get_enforcer()
    return json.dumps(
        {
            "policies": enforcer.get_policy(),
            "grouping": enforcer.get_grouping_policy(),
        },
        ensure_ascii=False,
    )

from deepclaw.web_backend.auth.security import (
    generate_access_token,
    hash_password,
    verify_password,
)
from deepclaw.web_backend.auth.store import AuthStore
from deepclaw.web_backend.common.errors import BusinessRuleError

# 用户名归一化规则：去空格并统一小写，避免大小写导致重复账号。
USERNAME_MAX_LENGTH = 64


def normalize_username(username: str) -> str:
    """归一化用户名，去除首尾空格并转小写。

    Args:
        username: 原始用户名。

    Returns:
        str: 归一化后的用户名。

    Raises:
        BusinessRuleError: 名称为空或过长时抛出。
    """
    normalized = username.strip().lower()
    if not normalized:
        raise BusinessRuleError("用户名不能为空。")
    if len(normalized) > USERNAME_MAX_LENGTH:
        raise BusinessRuleError(f"用户名长度不能超过 {USERNAME_MAX_LENGTH} 个字符。")
    return normalized


def normalize_optional_email(email: str | None) -> str | None:
    """归一化可选邮箱，空值返回 None。

    Args:
        email: 原始邮箱。

    Returns:
        str | None: 归一化邮箱或 None。
    """
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


class AuthService:
    """账号认证服务。

    Args:
        store: 账号存储。
        admin_username: 首次启动自举管理员用户名。
        admin_password: 首次启动自举管理员密码。
        token_expire_days: 访问令牌有效期天数。
        admin_email: 自举管理员可选邮箱。
    """

    def __init__(
        self,
        *,
        store: AuthStore,
        admin_username: str | None,
        admin_password: str | None,
        token_expire_days: int,
        admin_email: str | None = None,
    ):
        self.store = store
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.admin_email = admin_email
        self.token_expire_days = token_expire_days

    async def initialize(self):
        """启动时校正历史令牌有效期。

        Args:
            无。
        """
        await self.store.reconcile_access_token_expiry(expire_days=self.token_expire_days)

    async def register(self, *, username: str, password: str, email: str | None = None):
        """注册普通用户。

        Args:
            username: 登录用户名。
            password: 登录密码。
            email: 可选邮箱。

        Returns:
            AuthUser: 新建账号。

        Raises:
            BusinessRuleError: 用户名已存在时抛出。
        """
        normalized_username = normalize_username(username)
        if await self.store.get_user_by_username(normalized_username) is not None:
            raise BusinessRuleError("该用户名已被注册，请更换或直接登录。")
        return await self.store.create_user(
            username=normalized_username,
            password_hash=hash_password(password),
            role="user",
            email=normalize_optional_email(email),
        )

    async def login(self, *, username: str, password: str):
        """校验用户名和密码并签发访问令牌。

        Args:
            username: 登录用户名。
            password: 登录密码。

        Returns:
            IssuedAccessToken: 已签发的访问令牌。

        Raises:
            BusinessRuleError: 凭据错误或账号被禁用时抛出。
        """
        normalized_username = normalize_username(username)
        user = await self.store.get_user_by_username(normalized_username)
        if user is None or not verify_password(password, user.password_hash):
            raise BusinessRuleError("用户名或密码错误。")
        if not user.is_active:
            raise BusinessRuleError("当前账号已被禁用，请联系管理员。")

        return await self.store.issue_access_token(
            user=user,
            raw_token=generate_access_token(),
            expire_days=self.token_expire_days,
        )

    async def authenticate_token(self, token: str):
        """按访问令牌解析当前账号。

        Args:
            token: 原始访问令牌。
        """
        return await self.store.get_actor_by_token(token)

    async def issue_user_access_token(self, *, user_id: str):
        """为仓库内的受信任调用方签发短生命周期用户令牌。

        Args:
            user_id: 目标用户 ID。
        """
        user = await self.store.get_user_by_user_id(user_id)
        if user is None:
            raise BusinessRuleError("用户不存在。")
        if not user.is_active:
            raise BusinessRuleError("当前账号已被禁用，请联系管理员。")
        return await self.store.issue_access_token(
            user=user,
            raw_token=generate_access_token(),
            expire_days=1,
        )

    async def revoke_token(self, token: str) -> bool:
        """撤销访问令牌。

        Args:
            token: 原始访问令牌。
        """
        return await self.store.revoke_token(token)

    async def _validate_role(self, role: str) -> str:
        """校验角色存在于 RBAC 角色目录。

        Args:
            role: 待分配的角色标识。

        Returns:
            str: 去除首尾空白后的角色标识。

        Raises:
            BusinessRuleError: 角色为空或角色目录中不存在。
        """
        normalized_role = role.strip()
        if not normalized_role:
            raise BusinessRuleError("角色不能为空。")
        from deepclaw.web_backend.auth.rbac.store import get_rbac_policy_store

        if not await get_rbac_policy_store().role_exists(normalized_role):
            raise BusinessRuleError("指定角色不存在，请先在角色目录中创建。")
        return normalized_role

    async def _cleanup_user_role_edges(self, user_id: str) -> None:
        """尽力清理已删除用户遗留的 Casbin 角色关系。

        Args:
            user_id: 已删除用户 ID。
        """
        try:
            from deepclaw.web_backend.auth.rbac.store import get_rbac_policy_store

            await get_rbac_policy_store().cleanup_user_role_edges(user_id)
        except Exception:
            return

    async def create_user_as_admin(
        self,
        *,
        username: str,
        password: str,
        role: str,
        email: str | None = None,
    ):
        """管理员创建用户。

        Args:
            username: 登录用户名。
            password: 初始密码。
            role: 用户角色。
            email: 可选邮箱。
        """
        normalized_username = normalize_username(username)
        normalized_role = await self._validate_role(role)
        if await self.store.get_user_by_username(normalized_username) is not None:
            raise BusinessRuleError("该用户名已被注册，请更换。")
        return await self.store.create_user(
            username=normalized_username,
            password_hash=hash_password(password),
            role=normalized_role,
            email=normalize_optional_email(email),
        )

    async def list_users(self, *, search: str = ""):
        """查询用户列表。

        Args:
            search: 按用户名或邮箱模糊搜索。
        """
        return await self.store.list_users(search=search)

    async def update_user_role(self, *, user_id: str, role: str):
        """更新用户角色。

        Args:
            user_id: 目标用户 ID。
            role: 新角色。
        """
        normalized_role = await self._validate_role(role)
        target = await self.store.get_user_by_user_id(user_id)
        if target is None:
            raise BusinessRuleError("用户不存在。")
        if target.is_active and target.role == "admin" and normalized_role != "admin":
            if await self.store.count_active_admin_users() <= 1:
                raise BusinessRuleError("至少保留一个启用中的管理员账号。")
        return await self.store.update_user_role(user_id=user_id, role=normalized_role)

    async def update_user_status(self, *, user_id: str, is_active: bool):
        """启用或禁用用户，禁用时撤销全部令牌。

        Args:
            user_id: 目标用户 ID。
            is_active: 是否启用。
        """
        target = await self.store.get_user_by_user_id(user_id)
        if target is None:
            raise BusinessRuleError("用户不存在。")
        if target.is_active and not is_active and target.role == "admin":
            if await self.store.count_active_admin_users() <= 1:
                raise BusinessRuleError("至少保留一个启用中的管理员账号。")
        user = await self.store.update_user_status(user_id=user_id, is_active=is_active)
        if not is_active:
            await self.store.revoke_tokens_by_user_id(user_id)
        return user

    async def update_user_profile(
        self,
        *,
        user_id: str,
        username: str | None = None,
        email: str | None = None,
    ):
        """管理员修改用户用户名或邮箱。

        Args:
            user_id: 目标用户 ID。
            username: 新用户名；为 None 或空串表示不修改。
            email: 新邮箱；None 表示不修改，空串表示清空。

        Returns:
            AuthUser: 更新后的账号。

        Raises:
            BusinessRuleError: 用户名或邮箱已被其他账号占用时抛出。
        """
        normalized_username: str | None = None
        if username is not None and username.strip():
            normalized_username = normalize_username(username)
            existing = await self.store.get_user_by_username(normalized_username)
            if existing is not None and existing.user_id != user_id:
                raise BusinessRuleError("该用户名已被使用，请更换。")
        normalized_email: str | None = None
        if email is not None:
            normalized_email = normalize_optional_email(email)
            if normalized_email:
                taken = await self.store.get_user_by_email(normalized_email)
                if taken is not None and taken.user_id != user_id:
                    raise BusinessRuleError("该邮箱已被其他账号使用。")
        return await self.store.update_user_profile(
            user_id=user_id,
            username=normalized_username,
            email=normalized_email,
        )

    async def delete_user(self, *, user_id: str, operator_user_id: str | None = None):
        """删除用户账号，禁止删除自己或最后一个管理员。

        Args:
            user_id: 目标用户 ID。
            operator_user_id: 执行删除操作的管理员 ID。

        Returns:
            bool: 删除成功返回真。

        Raises:
            BusinessRuleError: 删除自己、删除最后一个管理员或账号不存在时抛出。
        """
        if operator_user_id and operator_user_id == user_id:
            raise BusinessRuleError("不能删除当前登录的账号。")
        target = await self.store.get_user_by_user_id(user_id)
        if target is None:
            raise BusinessRuleError("用户不存在。")
        if target.role == "admin" and await self.store.count_active_admin_users() <= 1:
            raise BusinessRuleError("至少保留一个启用中的管理员账号。")
        await self.store.revoke_tokens_by_user_id(user_id)
        deleted = await self.store.delete_user(user_id=user_id)
        await self._cleanup_user_role_edges(user_id)
        return deleted

    async def reset_user_password(self, *, user_id: str, password: str):
        """重置用户密码并撤销旧令牌。

        Args:
            user_id: 目标用户 ID。
            password: 新密码。
        """
        await self.store.revoke_tokens_by_user_id(user_id)
        return await self.store.update_user_password(
            user_id=user_id,
            password_hash=hash_password(password),
        )

    async def bootstrap_admin_if_needed(self):
        """确保配置的默认管理员账号存在且为可用的管理员身份。

        只补齐缺失的账号或错误角色，不会覆盖已有密码，避免把线上密码静默改回默认值。

        Args:
            无。

        Returns:
            AuthUser | None: 新建的管理员；无需变更时返回 None。
        """
        if not self.admin_username or not self.admin_password:
            return None
        normalized_username = normalize_username(self.admin_username)
        existing = await self.store.get_user_by_username(normalized_username)
        if existing is not None:
            if existing.role != "admin":
                return await self.store.update_user_role(
                    user_id=existing.user_id,
                    role="admin",
                )
            if not verify_password(self.admin_password, existing.password_hash):
                # 配置即默认口令声明的唯一来源：与配置不一致时同步，避免升级后无法登录。
                return await self.store.update_user_password(
                    user_id=existing.user_id,
                    password_hash=hash_password(self.admin_password),
                )
            return None
        return await self.store.create_user(
            username=normalized_username,
            password_hash=hash_password(self.admin_password),
            role="admin",
            email=normalize_optional_email(self.admin_email),
        )

_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """返回延迟初始化的认证服务。

    Args:
        无。

    Returns:
        AuthService: 进程内共享的认证服务。
    """
    global _auth_service
    if _auth_service is None:
        from deepclaw.settings import settings

        _auth_service = AuthService(
            store=AuthStore(),
            admin_username=settings.AUTH_ADMIN_USERNAME,
            admin_password=settings.AUTH_ADMIN_PASSWORD,
            token_expire_days=settings.AUTH_TOKEN_EXPIRE_DAYS,
            admin_email=settings.AUTH_ADMIN_EMAIL,
        )
    return _auth_service

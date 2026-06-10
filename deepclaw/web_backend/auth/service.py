from deepclaw.web_backend.auth.security import (
    generate_access_token,
    hash_password,
    verify_password,
)
from deepclaw.web_backend.auth.store import AuthStore


class AuthService:
    def __init__(
        self,
        *,
        store: AuthStore,
        admin_email: str | None,
        admin_password: str | None,
        token_expire_days: int,
    ):
        self.store = store
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.token_expire_days = token_expire_days
        self.store.reconcile_access_token_expiry(expire_days=token_expire_days)

    def register(self, *, email: str, password: str):
        normalized_email = email.strip().lower()
        if self.store.get_user_by_email(normalized_email):
            raise ValueError("该邮箱已注册，请直接登录。")
        return self.store.create_user(
            email=normalized_email,
            password_hash=hash_password(password),
            role="user",
        )

    def login(self, *, email: str, password: str):
        normalized_email = email.strip().lower()
        user = self.store.get_user_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            raise ValueError("邮箱或密码错误。")
        if not user.is_active:
            raise ValueError("当前账号已被禁用，请联系管理员。")

        return self.store.issue_access_token(
            user=user,
            raw_token=generate_access_token(),
            expire_days=self.token_expire_days,
        )

    def authenticate_token(self, token: str):
        return self.store.get_actor_by_token(token)

    def issue_user_access_token(self, *, user_id: str):
        """为仓库内的受信任调用方签发短生命周期用户令牌。"""
        user = self.store.get_user_by_user_id(user_id)
        if user is None:
            raise ValueError("用户不存在。")
        if not user.is_active:
            raise ValueError("当前账号已被禁用，请联系管理员。")
        return self.store.issue_access_token(
            user=user,
            raw_token=generate_access_token(),
            expire_days=1,
        )

    def revoke_token(self, token: str) -> bool:
        return self.store.revoke_token(token)

    def create_user_as_admin(self, *, email: str, password: str, role: str):
        normalized_email = email.strip().lower()
        if self.store.get_user_by_email(normalized_email):
            raise ValueError("该邮箱已注册，请直接登录。")
        return self.store.create_user(
            email=normalized_email,
            password_hash=hash_password(password),
            role=role,
        )

    def list_users(self, *, search: str = ""):
        return self.store.list_users(search=search)

    def update_user_role(self, *, user_id: str, role: str):
        return self.store.update_user_role(user_id=user_id, role=role)

    def update_user_status(self, *, user_id: str, is_active: bool):
        user = self.store.update_user_status(user_id=user_id, is_active=is_active)
        if not is_active:
            self.store.revoke_tokens_by_user_id(user_id)
        return user

    def reset_user_password(self, *, user_id: str, password: str):
        self.store.revoke_tokens_by_user_id(user_id)
        return self.store.update_user_password(
            user_id=user_id,
            password_hash=hash_password(password),
        )

    def bootstrap_admin_if_needed(self):
        if self.store.has_admin_user():
            return None
        if not self.admin_email or not self.admin_password:
            return None
        return self.store.create_user(
            email=self.admin_email.strip().lower(),
            password_hash=hash_password(self.admin_password),
            role="admin",
        )


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        from deepclaw.settings import settings

        _auth_service = AuthService(
            store=AuthStore(),
            admin_email=settings.AUTH_ADMIN_EMAIL,
            admin_password=settings.AUTH_ADMIN_PASSWORD,
            token_expire_days=settings.AUTH_TOKEN_EXPIRE_DAYS,
        )
    return _auth_service

import os
import uuid
from datetime import timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from langchain_api.web_backend.auth.models import (
    AccessTokenRecord,
    AuthUser,
    AuthenticatedActor,
    IssuedAccessToken,
    utc_now,
)
from langchain_api.web_backend.auth.security import hash_token
from langchain_api.constant import home_path


class AuthStore:
    def __init__(self, db_url: str | None = None):
        if db_url is None:
            os.makedirs(home_path, exist_ok=True)
            db_url = f"sqlite:///{os.path.join(home_path, 'auth.db')}"

        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        engine_kwargs: dict[str, object] = {"connect_args": connect_args}
        if db_url == "sqlite:///:memory:":
            engine_kwargs["poolclass"] = StaticPool

        self.engine = create_engine(db_url, echo=False, **engine_kwargs)
        SQLModel.metadata.create_all(self.engine)

    def reconcile_access_token_expiry(self, *, expire_days: int) -> None:
        max_lifetime = timedelta(days=expire_days)
        now = utc_now()
        with Session(self.engine) as session:
            records = list(session.exec(select(AccessTokenRecord)).all())
            changed = False
            for record in records:
                normalized_expires_at = min(
                    record.expires_at,
                    record.created_at + max_lifetime,
                )
                if normalized_expires_at <= now:
                    session.delete(record)
                    changed = True
                    continue
                if normalized_expires_at != record.expires_at:
                    record.expires_at = normalized_expires_at
                    session.add(record)
                    changed = True

            if changed:
                session.commit()

    def get_user_by_email(self, email: str) -> AuthUser | None:
        with Session(self.engine) as session:
            statement = select(AuthUser).where(AuthUser.email == email)
            return session.exec(statement).first()

    def get_user_by_user_id(self, user_id: str) -> AuthUser | None:
        with Session(self.engine) as session:
            statement = select(AuthUser).where(AuthUser.user_id == user_id)
            return session.exec(statement).first()

    def has_admin_user(self) -> bool:
        with Session(self.engine) as session:
            statement = select(AuthUser).where(AuthUser.role == "admin")
            return session.exec(statement).first() is not None

    def create_user(self, *, email: str, password_hash: str, role: str) -> AuthUser:
        with Session(self.engine) as session:
            now = utc_now()
            user = AuthUser(
                user_id=f"user_{uuid.uuid4().hex}",
                email=email,
                password_hash=password_hash,
                role=role,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def list_users(self, *, search: str = "") -> list[AuthUser]:
        with Session(self.engine) as session:
            statement = select(AuthUser).order_by(AuthUser.created_at.desc())
            if search:
                like = f"%{search}%"
                statement = statement.where(AuthUser.email.like(like))
            return list(session.exec(statement).all())

    def update_user_role(self, *, user_id: str, role: str) -> AuthUser:
        with Session(self.engine) as session:
            user = session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            ).first()
            if user is None:
                raise ValueError("用户不存在。")
            user.role = role
            user.updated_at = utc_now()
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def update_user_status(self, *, user_id: str, is_active: bool) -> AuthUser:
        with Session(self.engine) as session:
            user = session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            ).first()
            if user is None:
                raise ValueError("用户不存在。")
            user.is_active = is_active
            user.updated_at = utc_now()
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def update_user_password(self, *, user_id: str, password_hash: str) -> AuthUser:
        with Session(self.engine) as session:
            user = session.exec(
                select(AuthUser).where(AuthUser.user_id == user_id)
            ).first()
            if user is None:
                raise ValueError("用户不存在。")
            user.password_hash = password_hash
            user.updated_at = utc_now()
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def revoke_token(self, token: str) -> bool:
        token_hash = hash_token(token)
        with Session(self.engine) as session:
            record = session.exec(
                select(AccessTokenRecord).where(AccessTokenRecord.token_hash == token_hash)
            ).first()
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def revoke_tokens_by_user_id(self, user_id: str) -> int:
        with Session(self.engine) as session:
            records = list(
                session.exec(
                    select(AccessTokenRecord).where(AccessTokenRecord.user_id == user_id)
                ).all()
            )
            for record in records:
                session.delete(record)
            session.commit()
            return len(records)

    def issue_access_token(
        self,
        *,
        user: AuthUser,
        raw_token: str,
        expire_days: int,
    ) -> IssuedAccessToken:
        with Session(self.engine) as session:
            now = utc_now()
            record = AccessTokenRecord(
                user_id=user.user_id,
                token_hash=hash_token(raw_token),
                expires_at=now + timedelta(days=expire_days),
                last_used_at=now,
                created_at=now,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return IssuedAccessToken(token=raw_token, user=user, record=record)

    def get_actor_by_token(self, token: str) -> AuthenticatedActor:
        token_hash = hash_token(token)
        with Session(self.engine) as session:
            statement = select(AccessTokenRecord).where(
                AccessTokenRecord.token_hash == token_hash
            )
            record = session.exec(statement).first()
            if record is None:
                raise ValueError("登录状态已失效，请重新登录。")
            if record.expires_at <= utc_now():
                session.delete(record)
                session.commit()
                raise ValueError("登录状态已失效，请重新登录。")

            user = session.exec(
                select(AuthUser).where(AuthUser.user_id == record.user_id)
            ).first()
            if user is None:
                raise ValueError("登录状态已失效，请重新登录。")

            record.last_used_at = utc_now()
            session.add(record)
            session.commit()
            session.refresh(record)
            session.refresh(user)
            return AuthenticatedActor(user=user, record=record)

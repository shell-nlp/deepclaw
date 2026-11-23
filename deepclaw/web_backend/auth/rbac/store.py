from sqlalchemy import func, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.auth.models import AuthUser
from deepclaw.web_backend.auth.rbac.models import RbacCatalogRole, RbacPolicyRule, RbacRoleRule
from deepclaw.web_backend.db import resolve_metadata_db_url

_store: "RbacPolicyStore | None" = None

BUILTIN_ROLES = {"user": "普通用户", "admin": "管理员"}


class RoleCatalogError(Exception):
    """角色目录业务错误。

    Args:
        status_code: 对应的 HTTP 状态码。
        detail: 错误说明。
    """

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class RbacPolicyStore:
    """RBAC 策略持久化存储。

    Args:
        db_url: 数据库连接地址；为空时使用元数据数据库（默认 .deepclaw/rbac.db）。
    """

    def __init__(self, db_url: str | None = None, auth_db_url: str | None = None) -> None:
        from sqlalchemy.pool import NullPool

        self.db_url = db_url or resolve_metadata_db_url("rbac.db")
        self.auth_db_url = auth_db_url or resolve_metadata_db_url("auth.db")
        self._same_auth_database = self.db_url == self.auth_db_url
        # 策略可能在任何事件循环中读取，NullPool 避免连接绑定到已关闭的循环。
        self.engine = create_async_engine_from_url(
            self.db_url,
            poolclass=NullPool,
        )
        self.sessions = build_async_sessionmaker(self.engine)

    async def ensure_schema(self) -> None:
        """创建策略相关数据表，已存在时跳过。

        Args:
            无。
        """
        from sqlmodel import SQLModel

        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def ensure_catalog(self) -> None:
        """按旧策略主体与继承角色补齐目录，不创建权限策略。

        Args:
            无。
        """
        await self.ensure_schema()
        async with self.sessions() as session:
            candidates = set(BUILTIN_ROLES)
            candidates.update((await session.exec(select(RbacPolicyRule.subject))).all())
            for child, parent in (await session.exec(select(RbacRoleRule.child, RbacRoleRule.parent))).all():
                candidates.add(parent)
                # 认证账号 ID 以 user_ 开头；其余旧式 g 子节点是角色。
                if not child.startswith("user_") and child != "guest":
                    candidates.add(child)
            existing = set((await session.exec(select(RbacCatalogRole.id))).all())
            for role_id in sorted(candidates - existing):
                session.add(RbacCatalogRole(id=role_id, name=BUILTIN_ROLES.get(role_id, role_id)))
            if candidates - existing:
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()  # 其他实例已经补齐同一个角色。

    async def role_exists(self, role_id: str) -> bool:
        """判断角色标识是否已存在于兼容目录。

        Args:
            role_id: 不可变角色标识。
        """
        await self.ensure_catalog()
        async with self.sessions() as session:
            return (await session.get(RbacCatalogRole, role_id)) is not None

    async def list_catalog_roles(self) -> list[RbacCatalogRole]:
        """读取全部目录角色及已迁移历史主体。

        Args:
            无。
        """
        await self.ensure_catalog()
        async with self.sessions() as session:
            return list((await session.exec(select(RbacCatalogRole).order_by(RbacCatalogRole.id))).all())

    async def create_catalog_role(self, role_id: str, name: str, description: str) -> None:
        """创建目录角色，禁止和已有角色标识冲突。

        Args:
            role_id: 不可变角色标识。
            name: 角色显示名称。
            description: 角色说明。
        """
        await self.ensure_catalog()
        async with self.sessions() as session:
            session.add(RbacCatalogRole(id=role_id, name=name, description=description))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise RoleCatalogError(409, "角色标识已存在。") from exc

    async def update_catalog_role(self, role_id: str, name: str | None, description: str | None) -> None:
        """修改非内置角色的显示信息。

        Args:
            role_id: 不可变角色标识。
            name: 可选新名称。
            description: 可选新说明。
        """
        await self.ensure_catalog()
        async with self.sessions() as session:
            role = await session.get(RbacCatalogRole, role_id, with_for_update=True)
            if role is None:
                raise RoleCatalogError(404, "角色不存在。")
            if role_id in BUILTIN_ROLES:
                raise RoleCatalogError(409, "内置角色不可修改。")
            if name is not None:
                role.name = name
            if description is not None:
                role.description = description
            session.add(role)
            await session.commit()

    async def replace_catalog_permissions(self, role_id: str, permissions: list[tuple[str, str]]) -> None:
        """在单个事务中原子替换角色的全部直接权限。

        Args:
            role_id: 不可变角色标识。
            permissions: 路径与动作二元组列表。
        """
        await self.ensure_catalog()
        async with self.sessions() as session:
            role = await session.get(RbacCatalogRole, role_id, with_for_update=True)
            if role is None:
                raise RoleCatalogError(404, "角色不存在。")
            if role_id in BUILTIN_ROLES:
                raise RoleCatalogError(409, "内置角色权限不可修改。")
            rules = (await session.exec(select(RbacPolicyRule).where(RbacPolicyRule.subject == role_id))).all()
            for rule in rules:
                await session.delete(rule)
            await session.flush()
            for path, action in sorted(set(permissions)):
                session.add(RbacPolicyRule(subject=role_id, path=path, action=action))
            await session.commit()

    async def delete_catalog_role(self, role_id: str, user_count: int = 0) -> None:
        """删除未被使用的非内置角色，同时清理对应 p/g 规则。

        Args:
            role_id: 不可变角色标识。
            user_count: 认证库中使用该角色的用户数。
        """
        await self.ensure_catalog()
        async with self.sessions() as session:
            role = await session.get(RbacCatalogRole, role_id, with_for_update=True)
            if role is None:
                raise RoleCatalogError(404, "角色不存在。")
            if role_id in BUILTIN_ROLES:
                raise RoleCatalogError(409, "内置角色不可删除。")
            if user_count:
                raise RoleCatalogError(409, "角色仍有用户使用。")
            # 共享 PG 数据库可在同一事务重新核查用户，SQLite 分库由调用方预查。
            if self._same_auth_database:
                count = (
                    await session.exec(select(func.count()).select_from(AuthUser).where(AuthUser.role == role_id))
                ).one()
                if count:
                    raise RoleCatalogError(409, "角色仍有用户使用。")
            policies = (await session.exec(select(RbacPolicyRule).where(RbacPolicyRule.subject == role_id))).all()
            roles = (
                await session.exec(
                    select(RbacRoleRule).where((RbacRoleRule.child == role_id) | (RbacRoleRule.parent == role_id))
                )
            ).all()
            for rule in [*policies, *roles]:
                await session.delete(rule)
            await session.delete(role)
            await session.commit()

    async def count_catalog_users(self, role_id: str) -> int:
        """从认证用户表按角色计算实际使用人数。

        Args:
            role_id: 角色标识。
        """
        if self._same_auth_database:
            engine = self.engine
        else:
            engine = create_async_engine_from_url(self.auth_db_url)
        try:
            async with engine.connect() as connection:
                table_exists = await connection.run_sync(lambda sync_conn: inspect(sync_conn).has_table("authuser"))
            if not table_exists:
                return 0
            sessions = self.sessions if self._same_auth_database else build_async_sessionmaker(engine)
            async with sessions() as session:
                return (
                    await session.exec(select(func.count()).select_from(AuthUser).where(AuthUser.role == role_id))
                ).one()
        finally:
            if engine is not self.engine:
                await engine.dispose()

    async def cleanup_user_role_edges(self, user_id: str) -> None:
        """删除账号对应的全部旧式 g 绑定。

        Args:
            user_id: 被删除账号的用户标识。
        """
        await self.ensure_schema()
        async with self.sessions() as session:
            rules = (await session.exec(select(RbacRoleRule).where(RbacRoleRule.child == user_id))).all()
            for rule in rules:
                await session.delete(rule)
            await session.commit()

    async def is_initialized(self) -> bool:
        """判断策略表是否已经写入过基础策略。

        Args:
            无。

        Returns:
            bool: 存在任一策略行时返回真。
        """
        async with self.sessions() as session:
            policy_exists = (await session.exec(select(RbacPolicyRule).limit(1))).first() is not None
            role_exists = (await session.exec(select(RbacRoleRule).limit(1))).first() is not None
        return policy_exists or role_exists

    async def list_policies(self) -> list[RbacPolicyRule]:
        """列出全部策略行。

        Args:
            无。

        Returns:
            list[RbacPolicyRule]: 按主体和路径排序的策略行。
        """
        async with self.sessions() as session:
            return list(
                (
                    await session.exec(
                        select(RbacPolicyRule).order_by(
                            RbacPolicyRule.subject,
                            RbacPolicyRule.path,
                            RbacPolicyRule.action,
                        )
                    )
                ).all()
            )

    async def list_roles(self) -> list[RbacRoleRule]:
        """列出全部角色继承行。

        Args:
            无。

        Returns:
            list[RbacRoleRule]: 按父子角色排序的继承行。
        """
        async with self.sessions() as session:
            return list(
                (await session.exec(select(RbacRoleRule).order_by(RbacRoleRule.child, RbacRoleRule.parent))).all()
            )

    async def seed(self, policies: list[tuple[str, str, str]], roles: list[tuple[str, str]]) -> None:
        """把基础策略写入空库。

        Args:
            policies: (主体, 路径, 动作) 三元组列表。
            roles: (子角色, 父角色) 二元组列表。
        """
        async with self.sessions() as session:
            for subject, path, action in policies:
                session.add(RbacPolicyRule(subject=subject, path=path, action=action))
            for child, parent in roles:
                session.add(RbacRoleRule(child=child, parent=parent))
            await session.commit()

    async def add_policy(self, subject: str, path: str, action: str) -> RbacPolicyRule:
        """新增一条策略行，重复时返回已有行。

        Args:
            subject: 策略主体。
            path: 资源路径。
            action: 动作名称。

        Returns:
            RbacPolicyRule: 新增或已存在的策略行。
        """
        async with self.sessions() as session:
            existing = (
                await session.exec(
                    select(RbacPolicyRule).where(
                        RbacPolicyRule.subject == subject,
                        RbacPolicyRule.path == path,
                        RbacPolicyRule.action == action,
                    )
                )
            ).first()
            if existing is not None:
                return existing
            rule = RbacPolicyRule(subject=subject, path=path, action=action)
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    async def delete_policy(self, subject: str, path: str, action: str) -> bool:
        """删除一条策略行。

        Args:
            subject: 策略主体。
            path: 资源路径。
            action: 动作名称。

        Returns:
            bool: 删除成功时返回真。
        """
        async with self.sessions() as session:
            rule = (
                await session.exec(
                    select(RbacPolicyRule).where(
                        RbacPolicyRule.subject == subject,
                        RbacPolicyRule.path == path,
                        RbacPolicyRule.action == action,
                    )
                )
            ).first()
            if rule is None:
                return False
            await session.delete(rule)
            await session.commit()
            return True

    async def add_role(self, child: str, parent: str) -> RbacRoleRule:
        """新增一条角色继承行，重复时返回已有行。

        Args:
            child: 子角色或被赋予角色的用户 ID。
            parent: 父角色。

        Returns:
            RbacRoleRule: 新增或已存在的继承行。
        """
        async with self.sessions() as session:
            existing = (
                await session.exec(
                    select(RbacRoleRule).where(
                        RbacRoleRule.child == child,
                        RbacRoleRule.parent == parent,
                    )
                )
            ).first()
            if existing is not None:
                return existing
            rule = RbacRoleRule(child=child, parent=parent)
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    async def delete_role(self, child: str, parent: str) -> bool:
        """删除一条角色继承行。

        Args:
            child: 子角色或被赋予角色的用户 ID。
            parent: 父角色。

        Returns:
            bool: 删除成功时返回真。
        """
        async with self.sessions() as session:
            rule = (
                await session.exec(
                    select(RbacRoleRule).where(
                        RbacRoleRule.child == child,
                        RbacRoleRule.parent == parent,
                    )
                )
            ).first()
            if rule is None:
                return False
            await session.delete(rule)
            await session.commit()
            return True


def run_store_sync(coro):
    """在独立事件循环中执行存储协程，供同步的 Casbin 装载逻辑调用。

    已有运行中的事件循环时（例如异步测试上下文），新建线程执行，
    避免与当前循环的协程互相等待。

    Args:
        coro: 待执行的存储协程。

    Returns:
        协程执行结果。
    """
    import asyncio
    import threading

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[object] = []
    error: list[BaseException] = []

    def runner() -> None:
        """在新线程的独立事件循环中执行协程。

        Args:
            无。
        """
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # noqa: BLE001 - 需要把异常传回调用线程
            error.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0] if result else None


def get_rbac_policy_store() -> RbacPolicyStore:
    """返回延迟初始化的 RBAC 策略存储。

    Args:
        无。

    Returns:
        RbacPolicyStore: 进程内共享的策略存储。
    """
    global _store
    if _store is None:
        _store = RbacPolicyStore()
    return _store


async def close_rbac_policy_store() -> None:
    """释放策略存储连接池。

    Args:
        无。
    """
    global _store
    if _store is not None:
        await _store.engine.dispose()
        _store = None

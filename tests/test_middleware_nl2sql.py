from types import SimpleNamespace


def test_resolve_database_url_falls_back_to_settings(monkeypatch):
    """验证 NL2SQL 连接串会在缺少显式配置时回退到 settings。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.delenv("NL2SQL_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        nl2sql_module,
        "settings",
        SimpleNamespace(PG_DATABASE_URL="postgresql://settings-host:5432/app"),
        raising=False,
    )
    monkeypatch.setattr(nl2sql_module, "DATABASE_URL", None, raising=False)

    assert (
        nl2sql_module._resolve_database_url()
        == "postgresql://settings-host:5432/app"
    )


def test_oracle_thick_mode_ignores_lib_dir_on_linux(monkeypatch):
    """验证 Linux 下启用 thick 模式时不会向驱动传递 lib_dir。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.ddl.oracle as oracle_module

    init_calls: list[dict] = []
    connect_calls: list[dict] = []

    def fake_init_oracle_client(**kwargs):
        """记录 Oracle 客户端初始化参数。

        Args:
            **kwargs: 传入驱动初始化函数的关键字参数。
        """
        init_calls.append(kwargs)

    def fake_connect(**kwargs):
        """记录 Oracle 连接参数并返回占位连接结果。

        Args:
            **kwargs: 传入驱动连接函数的关键字参数。
        """
        connect_calls.append(kwargs)
        return "oracle-connection"

    monkeypatch.setenv("ORACLE_CLIENT_LIB_DIR", r"D:\instantclient_23_0")
    monkeypatch.setattr(
        oracle_module,
        "oracledb",
        SimpleNamespace(
            init_oracle_client=fake_init_oracle_client,
            connect=fake_connect,
        ),
    )
    monkeypatch.setattr(
        oracle_module,
        "platform",
        SimpleNamespace(system=lambda: "Linux"),
        raising=False,
    )

    result = oracle_module.OracleDdlFetcher._make_connection_thick(user="scott")

    assert result == "oracle-connection"
    assert init_calls == [{}]
    assert connect_calls == [{"user": "scott"}]


def test_resolve_schema_prefers_argument_then_env(monkeypatch):
    """验证 schema 解析优先使用显式参数，其次回退到环境变量。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.setenv("NL2SQL_SCHEMA", "GISTOOLS")

    assert nl2sql_module._resolve_schema("CUSTOM") == "CUSTOM"
    assert nl2sql_module._resolve_schema(None) == "GISTOOLS"


def test_validate_readonly_allows_leading_sql_comment():
    """验证只读校验允许前导 SQL 注释后再出现 SELECT。

    Args:
        无。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    sql = """
    -- 统计焦作数据
    SELECT COUNT(*)
    FROM TB_KR_GRP_SK_GRP_TOL_DAY
    """

    nl2sql_module._validate_readonly(sql)


def test_run_sql_returns_error_message_for_non_readonly_sql(monkeypatch):
    """验证 run_sql 遇到非只读语句时返回错误文本而不是抛异常。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.setenv("NL2SQL_DATABASE_URL", "oracle+oracledb://user:pwd@host:1521/?service_name=svc")

    run_sql_tool = nl2sql_module.NL2SQLMiddleware().get_run_sql_tool()

    result = run_sql_tool.invoke({"sql": "DELETE FROM TB_KR_GRP_SK_GRP_TOL_DAY"})

    assert result.startswith("SQL 执行失败：仅允许执行查询（SELECT）语句")


def test_get_user_ddl_passes_schema_to_fetcher(monkeypatch):
    """验证 get_user_ddl 会把解析后的 schema 传给 DDL 拉取器。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    captured: dict[str, object] = {}

    def fake_fetch_schema_ddl(database_url: str, *, table_names=None, schema=None):
        """记录 DDL 拉取入参并返回占位结果。

        Args:
            database_url: 目标数据库连接串。
            table_names: 可选的表名列表。
            schema: 可选的 schema 名称。
        """
        captured["database_url"] = database_url
        captured["schema"] = schema
        captured["table_names"] = table_names
        return "-- ddl"

    monkeypatch.setenv("NL2SQL_DATABASE_URL", "oracle+oracledb://user:pwd@host:1521/?service_name=svc")
    monkeypatch.setenv("NL2SQL_SCHEMA", "GISTOOLS")
    monkeypatch.delenv("NL2SQL_ALLOWED_TABLES", raising=False)
    monkeypatch.setattr(nl2sql_module, "fetch_schema_ddl", fake_fetch_schema_ddl)

    result = nl2sql_module.NL2SQLMiddleware().get_user_ddl()

    assert result == "-- ddl"
    assert captured == {
        "database_url": "oracle+oracledb://user:pwd@host:1521/?service_name=svc",
        "schema": "GISTOOLS",
        "table_names": None,
    }


def test_apply_schema_to_connection_sets_oracle_current_schema():
    """验证 Oracle 连接会切换到指定 schema。

    Args:
        无。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    executed: list[tuple[str, dict]] = []

    class FakeCursor:
        """用于记录执行语句的游标替身。"""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, **kwargs):
            """记录执行过的 SQL。

            Args:
                sql: 执行的 SQL 文本。
                **kwargs: SQL 绑定参数。
            """
            executed.append((sql, kwargs))

    class FakeConnection:
        """用于提供游标的连接替身。"""

        def cursor(self):
            """返回一个可记录 SQL 的游标。

            Args:
                无。
            """
            return FakeCursor()

    nl2sql_module._apply_schema_to_connection(
        FakeConnection(),
        "oracle+oracledb://user:pwd@host:1521/?service_name=svc",
        "GISTOOLS",
    )

    assert executed == [
        ("ALTER SESSION SET CURRENT_SCHEMA = GISTOOLS", {}),
    ]


def test_oracle_ddl_includes_column_comments():
    """验证 Oracle DDL 输出会追加字段注释语句。

    Args:
        无。
    """
    from deepclaw.middleware.nl2sql.ddl.oracle import OracleDdlFetcher

    executed_sql: list[str] = []
    responses = [
        [
            ("COL_A", "VARCHAR2", 32, None, None, "N", None, 32, "字段A说明"),
            ("COL_B", "NUMBER", None, 10, 2, "Y", None, None, "字段B说明"),
            ("COL_C", "DATE", None, None, None, "Y", None, None, None),
        ],
        [("COL_A",)],
    ]

    class FakeCursor:
        """用于模拟 Oracle 游标查询结果。"""

        def execute(self, sql: str, **kwargs):
            """记录执行语句。

            Args:
                sql: 当前执行的 SQL。
                **kwargs: 绑定参数。
            """
            executed_sql.append(sql)

        def fetchall(self):
            """按预设顺序返回查询结果。

            Args:
                无。
            """
            return responses.pop(0)

    ddl = OracleDdlFetcher()._build_create_table_ddl(
        FakeCursor(),
        "GISTOOLS",
        "TB_SAMPLE",
    )

    assert "COMMENT ON COLUMN \"TB_SAMPLE\".\"COL_A\" IS '字段A说明';" in ddl
    assert "COMMENT ON COLUMN \"TB_SAMPLE\".\"COL_B\" IS '字段B说明';" in ddl
    assert "COMMENT ON COLUMN \"TB_SAMPLE\".\"COL_C\"" not in ddl
    assert any("all_col_comments" in sql for sql in executed_sql)


def test_pg_ddl_includes_column_comments():
    """验证 PostgreSQL DDL 输出会追加字段注释语句。

    Args:
        无。
    """
    from deepclaw.middleware.nl2sql.ddl.pgsql import PgDdlFetcher

    responses = [
        [
            ("col_a", "character varying(32)", False, None, "字段A说明"),
            ("col_b", "integer", True, "0", "字段B说明"),
            ("col_c", "timestamp without time zone", True, None, None),
        ],
        [("col_a",)],
    ]

    class FakeCursor:
        """用于模拟 PostgreSQL 游标查询结果。"""

        def execute(self, sql: str, params):
            """记录执行语句。

            Args:
                sql: 当前执行的 SQL。
                params: SQL 参数。
            """
            _ = (sql, params)

        def fetchall(self):
            """按预设顺序返回查询结果。

            Args:
                无。
            """
            return responses.pop(0)

    ddl = PgDdlFetcher()._build_create_table_ddl(
        FakeCursor(),
        "public",
        "demo_table",
    )

    assert 'COMMENT ON COLUMN "demo_table"."col_a" IS \'字段A说明\';' in ddl
    assert 'COMMENT ON COLUMN "demo_table"."col_b" IS \'字段B说明\';' in ddl
    assert 'COMMENT ON COLUMN "demo_table"."col_c"' not in ddl


def test_join_table_ddls_uses_separator():
    """不同表的 DDL 片段之间应使用 --- 分隔。"""
    from deepclaw.middleware.nl2sql.ddl.base import BaseDdlFetcher

    result = BaseDdlFetcher.join_table_ddls(["CREATE TABLE a;", "CREATE TABLE b;"])
    assert result == "CREATE TABLE a;\n---\nCREATE TABLE b;"


def test_run_sql_applies_row_limit_before_execute(monkeypatch):
    """验证 run_sql 执行前会在 SQL 层注入行数限制。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    executed_sql: list[str] = []

    class FakeCursor:
        description = (("ID",), ("NAME",))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str):
            executed_sql.append(sql)

        def fetchmany(self, size: int):
            _ = size
            return [(1, "a"), (2, "b")]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setenv(
        "NL2SQL_DATABASE_URL",
        "oracle+oracledb://user:pwd@host:1521/?service_name=svc",
    )
    monkeypatch.setattr(
        nl2sql_module,
        "_make_connection",
        lambda database_url: FakeConnection(),
    )
    monkeypatch.setattr(
        nl2sql_module,
        "_apply_schema_to_connection",
        lambda conn, database_url, schema: None,
    )

    result = nl2sql_module.NL2SQLMiddleware().get_run_sql_tool().invoke({"sql": "SELECT * FROM TB_SAMPLE"})

    assert executed_sql == ["SELECT * FROM (\nSELECT * FROM TB_SAMPLE\n) nl2sql_row_limit WHERE ROWNUM <= 31"]
    assert "ID\tNAME" in result
    assert "1\ta" in result


def test_resolve_allowed_tables_prefers_argument_then_env(monkeypatch):
    """验证表白名单优先使用显式参数，其次环境变量，未配置则为全部表。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.setenv("NL2SQL_ALLOWED_TABLES", "TB_A, TB_B")

    assert nl2sql_module._resolve_allowed_tables(["TB_X"]) == ["TB_X"]
    assert nl2sql_module._resolve_allowed_tables(None) == ["TB_A", "TB_B"]

    monkeypatch.delenv("NL2SQL_ALLOWED_TABLES", raising=False)
    assert nl2sql_module._resolve_allowed_tables(None) is None
    assert nl2sql_module._resolve_allowed_tables([]) is None


def test_list_tables_tool_filters_by_allowed_tables(monkeypatch):
    """验证 list_tables_tool 仅返回白名单内的表。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.setenv("NL2SQL_DATABASE_URL", "oracle+oracledb://user:pwd@host:1521/?service_name=svc")
    monkeypatch.setenv("NL2SQL_ALLOWED_TABLES", "TB_A, TB_C")
    monkeypatch.setattr(
        nl2sql_module,
        "list_tables",
        lambda database_url, *, schema=None: ["TB_A", "TB_B", "TB_C"],
    )

    result = nl2sql_module.NL2SQLMiddleware().get_list_tables_tool().invoke({})

    assert "TB_A" in result
    assert "TB_C" in result
    assert "TB_B" not in result


def test_describe_tables_tool_rejects_disallowed_tables(monkeypatch):
    """验证 describe_tables_tool 拒绝查看白名单外的表。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.setenv("NL2SQL_DATABASE_URL", "oracle+oracledb://user:pwd@host:1521/?service_name=svc")
    monkeypatch.setenv("NL2SQL_ALLOWED_TABLES", "TB_A")
    monkeypatch.setattr(
        nl2sql_module,
        "fetch_schema_ddl",
        lambda database_url, *, table_names=None, schema=None: "should-not-call",
    )

    result = nl2sql_module.NL2SQLMiddleware().get_describe_tables_tool().invoke({"table_names": "TB_B"})

    assert result.startswith("无权查看表: TB_B")


def test_run_sql_rejects_disallowed_tables(monkeypatch):
    """验证 run_sql 拒绝查询白名单外的表。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    monkeypatch.setenv("NL2SQL_DATABASE_URL", "oracle+oracledb://user:pwd@host:1521/?service_name=svc")
    monkeypatch.setenv("NL2SQL_ALLOWED_TABLES", "TB_A")

    result = nl2sql_module.NL2SQLMiddleware().get_run_sql_tool().invoke({"sql": "SELECT * FROM TB_B"})

    assert "仅允许访问配置的表" in result
    assert "TB_B" in result


def test_get_user_ddl_passes_allowed_tables_to_fetcher(monkeypatch):
    """验证 get_user_ddl 配置白名单时会把 table_names 传给 DDL 拉取器。

    Args:
        monkeypatch: pytest 提供的环境与属性补丁工具。
    """
    import deepclaw.middleware.nl2sql.nl2sql as nl2sql_module

    captured: dict[str, object] = {}

    def fake_fetch_schema_ddl(database_url: str, *, table_names=None, schema=None):
        captured["table_names"] = table_names
        captured["schema"] = schema
        return "-- ddl"

    monkeypatch.setenv("NL2SQL_DATABASE_URL", "oracle+oracledb://user:pwd@host:1521/?service_name=svc")
    monkeypatch.setenv("NL2SQL_SCHEMA", "GISTOOLS")
    monkeypatch.setattr(nl2sql_module, "fetch_schema_ddl", fake_fetch_schema_ddl)

    result = nl2sql_module.NL2SQLMiddleware(allowed_tables=["TB_A", "TB_B"]).get_user_ddl()

    assert result == "-- ddl"
    assert captured["table_names"] == ["TB_A", "TB_B"]
    assert captured["schema"] == "GISTOOLS"

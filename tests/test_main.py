import types


def test_configure_windows_event_loop_policy_sets_selector_policy(monkeypatch):
    from deepclaw import main

    calls = []

    class FakePolicy:
        pass

    monkeypatch.setattr(main.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(
        main.asyncio,
        "WindowsSelectorEventLoopPolicy",
        FakePolicy,
        raising=False,
    )
    monkeypatch.setattr(main.asyncio, "set_event_loop_policy", calls.append)

    main.configure_windows_event_loop_policy()

    assert len(calls) == 1
    assert isinstance(calls[0], FakePolicy)


def _install_fake_uvicorn(monkeypatch, calls):
    """把 main 的 uvicorn 与 threading 换成只记录调用的替身。

    Args:
        monkeypatch: pytest 提供的对象替换工具。
        calls: 记录调用顺序的列表。
    """
    from deepclaw import main

    class FakeConfig:
        def __init__(self, app, host, port, loop):
            """记录 Config 构造参数。

            Args:
                app: 传入的 FastAPI 应用。
                host: 监听地址。
                port: 监听端口。
                loop: 事件循环模式。
            """
            calls.append(("config", app, host, port, loop))
            self.host = host
            self.port = port
            self.loop = loop

    class FakeServer:
        def __init__(self, config):
            """记录 Server 构造参数。

            Args:
                config: 传入的 uvicorn 配置。
            """
            calls.append(("server", config.host, config.port, config.loop))
            self.started = False
            self.should_exit = False

        def run(self):
            """记录一次 server.run 调用。"""
            calls.append("run")

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            """记录线程参数但不真正启动。

            Args:
                target: 线程入口函数。
                args: 入口函数参数。
                daemon: 是否守护线程。
            """
            calls.append(("thread", target, args, daemon))

        def start(self):
            """记录线程启动动作。"""
            calls.append("thread.start")

    monkeypatch.setattr(
        main,
        "uvicorn",
        types.SimpleNamespace(Config=FakeConfig, Server=FakeServer),
        raising=False,
    )
    monkeypatch.setattr(
        main,
        "threading",
        types.SimpleNamespace(Thread=FakeThread),
        raising=False,
    )


def _assert_run_sequence(calls, app, loop_mode):
    """断言 run 的调用顺序：先设策略，再装配 Server，最后启动。

    Args:
        calls: 记录的调用序列。
        app: create_app 返回的应用。
        loop_mode: 期望的事件循环模式。
    """
    from deepclaw import main

    assert calls[0] == "policy"
    assert calls[1] == ("config", app, "0.0.0.0", 7869, loop_mode)
    assert calls[2] == ("server", "0.0.0.0", 7869, loop_mode)

    thread_call = calls[3]
    assert thread_call[0] == "thread"
    assert thread_call[1] is main.log_urls_when_server_ready
    assert thread_call[3] is True

    assert calls[4] == "thread.start"
    assert calls[5] == "run"


def test_run_configures_event_loop_policy_before_starting_uvicorn(monkeypatch):
    from deepclaw import main

    calls = []
    app = object()

    monkeypatch.setattr(
        main,
        "configure_windows_event_loop_policy",
        lambda: calls.append("policy"),
    )
    monkeypatch.setattr(main, "create_app", lambda: app, raising=False)
    _install_fake_uvicorn(monkeypatch, calls)

    main.run()

    _assert_run_sequence(calls, app, "none")


def test_run_uses_auto_loop_outside_windows(monkeypatch):
    from deepclaw import main

    calls = []
    app = object()

    monkeypatch.setattr(main.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(main, "create_app", lambda: app, raising=False)
    monkeypatch.setattr(
        main,
        "configure_windows_event_loop_policy",
        lambda: calls.append("policy"),
    )
    _install_fake_uvicorn(monkeypatch, calls)

    main.run()

    _assert_run_sequence(calls, app, "auto")


def test_log_urls_when_server_ready_waits_for_port_binding(monkeypatch):
    """端口绑定成功后才记录访问地址；端口占用提前退出时不输出。"""
    from deepclaw import main

    logged = []
    monkeypatch.setattr(main, "log_startup_urls", lambda: logged.append("urls"))
    monkeypatch.setattr(
        main,
        "time",
        types.SimpleNamespace(sleep=lambda seconds: None),
        raising=False,
    )

    main.log_urls_when_server_ready(
        types.SimpleNamespace(started=False, should_exit=True)
    )
    assert logged == []

    main.log_urls_when_server_ready(
        types.SimpleNamespace(started=True, should_exit=False)
    )
    assert logged == ["urls"]

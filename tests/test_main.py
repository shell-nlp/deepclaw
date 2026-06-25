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
    monkeypatch.setattr(
        main,
        "uvicorn",
        types.SimpleNamespace(
            run=lambda passed_app, host, port, loop: calls.append(
                ("uvicorn", passed_app, host, port, loop)
            )
        ),
        raising=False,
    )

    main.run()

    assert calls == ["policy", ("uvicorn", app, "0.0.0.0", 7869, "none")]


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
    monkeypatch.setattr(
        main,
        "uvicorn",
        types.SimpleNamespace(
            run=lambda passed_app, host, port, loop: calls.append(
                ("uvicorn", passed_app, host, port, loop)
            )
        ),
        raising=False,
    )

    main.run()

    assert calls == ["policy", ("uvicorn", app, "0.0.0.0", 7869, "auto")]

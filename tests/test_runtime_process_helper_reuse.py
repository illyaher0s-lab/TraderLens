from types import SimpleNamespace

import pytest

from scripts import runtime_process_helpers as helpers


def test_ensure_backend_reuses_listener_that_exposes_mounted_research_api(monkeypatch):
    """A running TraderLens backend must survive a browser acceptance rerun."""

    monkeypatch.setattr(helpers, "get_port_owner_pid", lambda port: 42)
    monkeypatch.setattr(
        helpers.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200),
    )
    start_calls = []
    monkeypatch.setattr(helpers, "start_backend", lambda **kwargs: start_calls.append(kwargs))

    process, reused = helpers.ensure_traderlens_backend(port=8010)

    assert process is None
    assert reused is True
    assert start_calls == []


def test_ensure_backend_refuses_unrecognized_listener_without_killing_it(monkeypatch):
    """Acceptance must fail loudly instead of killing another app on port 8010."""

    monkeypatch.setattr(helpers, "get_port_owner_pid", lambda port: 42)
    monkeypatch.setattr(
        helpers.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=404),
    )

    with pytest.raises(RuntimeError, match="not a TraderLens backend"):
        helpers.ensure_traderlens_backend(port=8010)


def test_ensure_backend_restarts_verified_stale_traderlens_listener(monkeypatch):
    """A stale TraderLens process lacking Workbench routes may be safely replaced."""

    monkeypatch.setattr(helpers, "get_port_owner_pid", lambda port: 42)
    monkeypatch.setattr(helpers, "is_traderlens_backend", lambda port: False)
    monkeypatch.setattr(
        helpers,
        "get_process_command_line",
        lambda pid: "python -m uvicorn backend.app.main:app --port 8010 --workers 1",
    )
    released = []
    monkeypatch.setattr(helpers, "release_port", lambda port: released.append(port))
    started = SimpleNamespace(pid=99)
    monkeypatch.setattr(helpers, "start_backend", lambda **kwargs: started)

    process, reused = helpers.ensure_traderlens_backend(port=8010)

    assert process is started
    assert reused is False
    assert released == [8010]


def test_ensure_frontend_reuses_traderlens_workbench(monkeypatch):
    """A running TraderLens frontend must survive a browser acceptance rerun."""

    monkeypatch.setattr(helpers, "get_port_owner_pid", lambda port: 43)
    monkeypatch.setattr(
        helpers.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            text="<title>TraderLens</title> 输入消息",
        ),
    )
    start_calls = []
    monkeypatch.setattr(helpers, "start_frontend", lambda **kwargs: start_calls.append(kwargs))

    process, reused = helpers.ensure_traderlens_frontend(port=3010)

    assert process is None
    assert reused is True
    assert start_calls == []


def test_ensure_frontend_refuses_unrecognized_listener_without_killing_it(monkeypatch):
    """Acceptance must not kill another app that happens to use port 3010."""

    monkeypatch.setattr(helpers, "get_port_owner_pid", lambda port: 43)
    monkeypatch.setattr(
        helpers.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, text="other app"),
    )

    with pytest.raises(RuntimeError, match="not a TraderLens frontend"):
        helpers.ensure_traderlens_frontend(port=3010)


def test_ensure_frontend_restarts_verified_stale_traderlens_listener(monkeypatch, tmp_path):
    """An unresponsive Next process from this workspace may be safely replaced."""

    monkeypatch.setattr(helpers, "get_port_owner_pid", lambda port: 43)
    monkeypatch.setattr(helpers, "is_traderlens_frontend", lambda port: False)
    monkeypatch.setattr(
        helpers,
        "get_process_command_line",
        lambda pid: f"node {tmp_path / 'node_modules' / 'next' / 'server.js'}",
    )
    released = []
    monkeypatch.setattr(helpers, "release_port", lambda port: released.append(port))
    started = SimpleNamespace(pid=100)
    monkeypatch.setattr(helpers, "start_frontend", lambda **kwargs: started)

    process, reused = helpers.ensure_traderlens_frontend(port=3010, project_root=tmp_path)

    assert process is started
    assert reused is False
    assert released == [3010]

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace


def test_windows_launchers_keep_crlf_and_absolute_server_identity():
    root = Path(__file__).resolve().parents[2]
    for name in ('start.bat', 'stop.bat', 'setup.bat'):
        data = (root / name).read_bytes()
        assert b'\r\n' in data
        assert b'\n' not in data.replace(b'\r\n', b'')
    assert '"%~dp0scripts\\run_server.py"' in (root / 'start.bat').read_text(encoding='utf-8')


def test_find_port_skips_an_occupied_loopback_port():
    from scripts import run_server

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        preferred = occupied.getsockname()[1]
        if preferred > 65435:
            return
        selected = run_server._find_port("127.0.0.1", preferred)
        assert preferred < selected < preferred + 100


def test_existing_server_removes_a_stale_record(tmp_path, monkeypatch):
    from scripts import run_server

    record_path = tmp_path / "server.json"
    record_path.write_text(json.dumps({"pid": 123, "url": "http://127.0.0.1:8000"}), encoding="utf-8")
    monkeypatch.setattr(run_server, "SERVER_RECORD", record_path)
    monkeypatch.setattr(run_server, "_is_record_process_alive", lambda _record: False)

    assert run_server._existing_server() is None
    assert not record_path.exists()


def test_existing_server_respects_browser_opt_out(tmp_path, monkeypatch):
    from scripts import run_server

    monkeypatch.setattr(run_server, "RUN_DIR", tmp_path)
    monkeypatch.setattr(run_server, "SERVER_RECORD", tmp_path / "server.json")
    monkeypatch.setattr(run_server, "_load_env_file", lambda: None)
    monkeypatch.setattr(run_server, "_existing_server", lambda: {"url": "http://127.0.0.1:8123"})
    opened: list[str] = []
    monkeypatch.setattr(run_server.webbrowser, "open", opened.append)
    monkeypatch.setenv("ISU_OPEN_BROWSER", "0")

    assert run_server.main() == 0
    assert opened == []


def test_stop_server_clears_record_for_a_missing_process(tmp_path, monkeypatch):
    from scripts import stop_server

    class NoSuchProcess(Exception):
        pass

    def missing_process(_pid: int):
        raise NoSuchProcess()

    record_path = tmp_path / "server.json"
    record_path.write_text(json.dumps({"pid": 123, "create_time": 1}), encoding="utf-8")
    monkeypatch.setattr(stop_server, "SERVER_RECORD", record_path)
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(NoSuchProcess=NoSuchProcess, Process=missing_process))

    assert stop_server.main() == 0
    assert not record_path.exists()


def test_stop_server_never_terminates_an_unrelated_reused_pid(tmp_path, monkeypatch):
    from scripts import stop_server

    class FakeProcess:
        terminated = False

        def cmdline(self):
            return ["python", "unrelated-service.py"]

        def create_time(self):
            return 10.0

        def terminate(self):
            self.terminated = True

    process = FakeProcess()
    record_path = tmp_path / "server.json"
    record_path.write_text(json.dumps({"pid": 456, "create_time": 10}), encoding="utf-8")
    monkeypatch.setattr(stop_server, "SERVER_RECORD", record_path)
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            NoSuchProcess=type("NoSuchProcess", (Exception,), {}),
            TimeoutExpired=type("TimeoutExpired", (Exception,), {}),
            Process=lambda _pid: process,
        ),
    )

    assert stop_server.main() == 1
    assert process.terminated is False
    assert record_path.exists()

import subprocess
import sys
import threading
import time

import pytest

from indiafacts import runner


class FakeProc:
    def __init__(self, hang=False):
        self.stderr = iter([]) if not hang else self
        self.hang, self.killed = hang, threading.Event()
        self.args = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.hang:
            self.killed.wait(5)                  # blocks until killed, like a child that prints nothing
            raise StopIteration
        raise StopIteration

    def wait(self):
        return 1

    def kill(self):
        self.killed.set()


def capture(monkeypatch, proc=None):
    seen = {}

    def popen(argv, **kw):
        seen["argv"], seen["env"], seen["kw"] = argv, kw.get("env", {}), kw
        return proc or FakeProc()

    monkeypatch.setattr(subprocess, "Popen", popen)
    return seen


def test_rs1_server_runs_never_remember_anything(monkeypatch):
    seen = capture(monkeypatch)
    with pytest.raises(ValueError):
        runner.subprocess_runner({"ticker": "TCS.NS"}, lambda p: None)
    assert "--no-remember" in seen["argv"]


def test_rs2_secrets_do_not_reach_the_child(monkeypatch):
    for k, v in {"GOOGLE_API_KEY": "a", "INDIAFACTS_MCP_TOKEN": "b", "MY_SECRET": "c", "DB_PASSWORD": "d", "OPENAI_API_KEY": "e", "PATH": "/usr/bin"}.items():
        monkeypatch.setenv(k, v)
    seen = capture(monkeypatch)
    with pytest.raises(ValueError):
        runner.subprocess_runner({"ticker": "TCS.NS"}, lambda p: None)
    assert set(seen["env"]) & {"GOOGLE_API_KEY", "INDIAFACTS_MCP_TOKEN", "MY_SECRET", "DB_PASSWORD", "OPENAI_API_KEY"} == set()
    assert seen["env"].get("PATH") == "/usr/bin"


def test_rs3_a_silent_hanging_child_is_killed_at_the_deadline(monkeypatch):
    monkeypatch.setattr(runner, "TIMEOUT_SECONDS", 0.3)
    proc = FakeProc(hang=True)
    capture(monkeypatch, proc)
    t0 = time.time()
    with pytest.raises((TimeoutError, ValueError)):
        runner.subprocess_runner({"ticker": "TCS.NS"}, lambda p: None)
    assert proc.killed.is_set() and time.time() - t0 < 3

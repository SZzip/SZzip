"""Offline tests for config resolution and CLI argument handling."""

from __future__ import annotations

import json

import pytest

from edoop.cli import _parse_data_arg, _parse_kv, build_parser, main
from edoop.config import Config
from edoop.errors import EdoopError


def test_parse_kv():
    assert _parse_kv(["a=1", "b=two"]) == {"a": "1", "b": "two"}
    with pytest.raises(EdoopError):
        _parse_kv(["bad"])


def test_parse_data_inline_and_file(tmp_path):
    assert _parse_data_arg('{"x": 1}') == {"x": 1}
    p = tmp_path / "body.json"
    p.write_text('{"y": 2}')
    assert _parse_data_arg(f"@{p}") == {"y": 2}
    assert _parse_data_arg(None) is None
    with pytest.raises(EdoopError):
        _parse_data_arg("{not json}")


def test_config_env_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("EDOOP_BASE_URL", "https://x.edoop.test/")
    monkeypatch.setenv("EDOOP_EMAIL", "a@b.de")
    monkeypatch.setenv("EDOOP_PASSWORD", "pw")
    monkeypatch.setenv("EDOOP_CONFIG", str(tmp_path / "cfg.json"))
    monkeypatch.setenv("EDOOP_ENDPOINTS", json.dumps({"me": "/api/v2/me"}))
    cfg = Config.load()
    assert cfg.base_url == "https://x.edoop.test"  # trailing slash stripped
    assert cfg.email == "a@b.de"
    assert cfg.password == "pw"
    assert cfg.endpoints["me"] == "/api/v2/me"


def test_config_never_persists_password(tmp_path, monkeypatch):
    monkeypatch.setenv("EDOOP_CONFIG", str(tmp_path / "cfg.json"))
    from edoop.config import write_config

    with pytest.raises(EdoopError):
        write_config({"password": "leak"})


def test_parser_builds_all_subcommands():
    parser = build_parser()
    for cmd in ["login", "logout", "whoami", "children", "messages", "absences", "appointments", "api", "config"]:
        args = parser.parse_args([cmd] if cmd != "api" else ["api", "GET", "/x"])
        assert hasattr(args, "func")


def test_main_no_command_returns_1(capsys):
    assert main([]) == 1


def test_config_show_runs(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDOOP_CONFIG", str(tmp_path / "cfg.json"))
    monkeypatch.setenv("EDOOP_STATE_DIR", str(tmp_path))
    rc = main(["config", "show"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "base_url" in out


def test_broken_pipe_exits_quietly(monkeypatch, capsys):
    # Simulate a downstream `| head` closing the pipe: the command's handler
    # raises BrokenPipeError and main() must swallow it (return 141), not crash.
    import edoop.cli as cli

    def boom(_args):
        raise BrokenPipeError()

    monkeypatch.setattr(cli, "cmd_whoami", boom)
    # Rebuild parser dispatch by calling through main with a command that maps
    # to the patched function.
    parser = cli.build_parser()
    args = parser.parse_args(["whoami"])
    args.func = boom
    monkeypatch.setattr(cli, "build_parser", lambda: _StubParser(args))
    rc = cli.main(["whoami"])
    assert rc == 141


class _StubParser:
    def __init__(self, args):
        self._args = args

    def parse_args(self, argv=None):
        return self._args

    def print_help(self):
        pass


def test_config_endpoints_lists_defaults(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDOOP_CONFIG", str(tmp_path / "cfg.json"))
    rc = main(["config", "endpoints"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "messages_list" in out

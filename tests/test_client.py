"""Offline tests for the client/auth layer using requests-mock."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests_mock

from edoop.client import EdoopClient, _find_token
from edoop.config import Config
from edoop.errors import AuthError, NotLoggedInError
from edoop.session import Session


def make_config(tmp_path: Path, **kw) -> Config:
    cfg = Config.load(base_url="https://edoop.test", email="p@example.com", password="secret", **kw)
    cfg.session_file = tmp_path / "session.json"
    cfg.config_file = tmp_path / "config.json"
    return cfg


def test_find_token_variants():
    assert _find_token({"token": "abc"}) == "abc"
    assert _find_token({"access_token": "xyz"}) == "xyz"
    assert _find_token({"data": {"api_token": "deep"}}) == "deep"
    assert _find_token({"user": {"name": "x"}}) is None
    assert _find_token("nope") is None


def test_login_token_flow_persists_session(tmp_path):
    cfg = make_config(tmp_path)
    with requests_mock.Mocker() as m:
        m.get("https://edoop.test/sanctum/csrf-cookie", status_code=204)
        m.post("https://edoop.test/api/login", json={"token": "T0KEN", "user": {"id": 1}})
        client = EdoopClient(cfg, session=Session())
        session = client.login("p@example.com", "secret")

    assert session.token == "T0KEN"
    assert session.user == {"id": 1}
    assert cfg.session_file.exists()
    saved = json.loads(cfg.session_file.read_text())
    assert saved["token"] == "T0KEN"
    # Auth header is applied for subsequent requests.
    assert client.http.headers["Authorization"] == "Bearer T0KEN"


def test_login_probes_candidates_until_success(tmp_path):
    cfg = make_config(tmp_path)
    with requests_mock.Mocker() as m:
        m.get("https://edoop.test/sanctum/csrf-cookie", status_code=204)
        m.post("https://edoop.test/api/login", status_code=404)
        m.post("https://edoop.test/api/auth/login", json={"access_token": "AT"})
        client = EdoopClient(cfg, session=Session())
        session = client.login("p@example.com", "secret")
    assert session.token == "AT"


def test_login_rejected_credentials_raises(tmp_path):
    cfg = make_config(tmp_path)
    with requests_mock.Mocker() as m:
        m.get("https://edoop.test/sanctum/csrf-cookie", status_code=204)
        m.post("https://edoop.test/api/login", status_code=422, json={"message": "invalid"})
        client = EdoopClient(cfg, session=Session())
        with pytest.raises(AuthError):
            client.login("p@example.com", "secret")


def test_login_cookie_only_flow(tmp_path):
    cfg = make_config(tmp_path)
    with requests_mock.Mocker() as m:
        m.get("https://edoop.test/sanctum/csrf-cookie", status_code=204)
        m.post(
            "https://edoop.test/api/login",
            json={"ok": True},
            cookies={"edoop_session": "abc"},
        )
        client = EdoopClient(cfg, session=Session())
        session = client.login("p@example.com", "secret")
    assert any(c["name"] == "edoop_session" for c in session.cookies)


def test_request_requires_auth(tmp_path):
    cfg = make_config(tmp_path)
    client = EdoopClient(cfg, session=Session())  # empty session
    with pytest.raises(NotLoggedInError):
        client.messages()


def test_request_401_maps_to_not_logged_in(tmp_path):
    cfg = make_config(tmp_path)
    sess = Session(token="T", base_url=cfg.base_url)
    client = EdoopClient(cfg, session=sess)
    with requests_mock.Mocker() as m:
        m.get("https://edoop.test/api/channels", status_code=401)
        with pytest.raises(NotLoggedInError):
            client.messages()


def test_high_level_endpoints_use_overrides(tmp_path):
    cfg = make_config(tmp_path, endpoints={"messages_list": "/api/v9/channels"})
    sess = Session(token="T", base_url=cfg.base_url)
    client = EdoopClient(cfg, session=sess)
    with requests_mock.Mocker() as m:
        m.get("https://edoop.test/api/v9/channels", json=[{"id": "c1"}])
        data = client.messages()
    assert data == [{"id": "c1"}]

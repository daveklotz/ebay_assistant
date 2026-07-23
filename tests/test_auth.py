from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ebay_assistant import auth
from ebay_assistant.auth import AuthError, get_access_token
from ebay_assistant.config import Config, Credentials


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def make_config(tmp_path) -> Config:
    return Config(
        environment="production",
        days_back=7,
        email_copy_to_sender=False,
        config_dir=tmp_path,
    )


def make_creds() -> Credentials:
    return Credentials(
        app_id="app",
        cert_id="cert",
        refresh_token="v^1.1#rt",
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=400),
    )


def test_refresh_and_cache(tmp_path, monkeypatch):
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(url)
        return FakeResponse(200, {"access_token": "tok123", "expires_in": 7200})

    monkeypatch.setattr(auth.requests, "post", fake_post)
    config, creds = make_config(tmp_path), make_creds()
    assert get_access_token(config, creds) == "tok123"
    assert get_access_token(config, creds) == "tok123"
    assert len(calls) == 1
    assert (tmp_path / "token_cache.json").exists()


def test_invalid_grant(tmp_path, monkeypatch):
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda *a, **k: FakeResponse(400, {"error": "invalid_grant"}),
    )
    with pytest.raises(AuthError, match="init --refresh-token"):
        get_access_token(make_config(tmp_path), make_creds())


def test_bad_keyset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        auth.requests, "post", lambda *a, **k: FakeResponse(401, {})
    )
    with pytest.raises(AuthError, match="App ID / Cert ID"):
        get_access_token(make_config(tmp_path), make_creds())


def test_exchange_authorization_code(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        captured.update(data)
        return FakeResponse(
            200,
            {
                "access_token": "at",
                "expires_in": 7200,
                "refresh_token": "v^1.1#rt-new",
                "refresh_token_expires_in": 47304000,
            },
        )

    monkeypatch.setattr(auth.requests, "post", fake_post)
    access, refresh, expires_at = auth.exchange_authorization_code(
        "https://api.ebay.com", "app", "cert", "v^1.1#code", "Me-App-xyz"
    )
    assert refresh == "v^1.1#rt-new"
    assert access == "at"
    assert captured["grant_type"] == "authorization_code"
    assert captured["code"] == "v^1.1#code"
    assert captured["redirect_uri"] == "Me-App-xyz"
    assert expires_at.tzinfo is not None


def test_exchange_expired_code(monkeypatch):
    monkeypatch.setattr(
        auth.requests,
        "post",
        lambda *a, **k: FakeResponse(400, {"error": "invalid_grant"}),
    )
    with pytest.raises(AuthError, match="single-use"):
        auth.exchange_authorization_code(
            "https://api.ebay.com", "app", "cert", "stale", "Me-App-xyz"
        )

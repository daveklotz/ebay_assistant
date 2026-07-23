"""Configuration, credentials, and message-template storage.

Everything lives in ~/.config/ebay_assistant/ (override with the
EBAY_ASSISTANT_CONFIG_DIR environment variable):

    config.toml       non-secret settings, meant to be hand-edited
    credentials.json  eBay keyset + OAuth refresh token (mode 0600)
    token_cache.json  cached short-lived access token (mode 0600)
    template.txt      the message template, meant to be hand-edited
    state.json        which orders have already been messaged
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

API_BASE = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}

DEFAULT_TEMPLATE = """\
Hi! Just a quick note to let you know I dropped {package_desc} off at the post office — it's on the way to you. Thanks so much for your purchase!
"""

CONFIG_FILE = "config.toml"
CREDENTIALS_FILE = "credentials.json"
TOKEN_CACHE_FILE = "token_cache.json"
TEMPLATE_FILE = "template.txt"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass
class Config:
    environment: str
    days_back: int
    email_copy_to_sender: bool
    config_dir: Path

    @property
    def api_base(self) -> str:
        return API_BASE[self.environment]


@dataclass
class Credentials:
    app_id: str
    cert_id: str
    refresh_token: str
    refresh_token_expires_at: datetime | None


def config_dir() -> Path:
    override = os.environ.get("EBAY_ASSISTANT_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "ebay_assistant"


def ensure_config_dir() -> Path:
    path = config_dir()
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def load_config() -> Config:
    path = config_dir() / CONFIG_FILE
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(
            f"no config found at {path} — run `ebay-assistant init` first"
        ) from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from None
    environment = raw.get("environment", "production")
    if environment not in API_BASE:
        raise ConfigError(
            f'invalid environment "{environment}" in {path} '
            '(use "production" or "sandbox")'
        )
    return Config(
        environment=environment,
        days_back=int(raw.get("days_back", 7)),
        email_copy_to_sender=bool(raw.get("email_copy_to_sender", False)),
        config_dir=path.parent,
    )


def load_credentials() -> Credentials:
    path = config_dir() / CREDENTIALS_FILE
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(
            f"no credentials found at {path} — run `ebay-assistant init` first"
        ) from None
    except ValueError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from None
    try:
        return Credentials(
            app_id=raw["app_id"],
            cert_id=raw["cert_id"],
            refresh_token=raw["refresh_token"],
            refresh_token_expires_at=parse_datetime(raw.get("refresh_token_expires_at")),
        )
    except KeyError as exc:
        raise ConfigError(
            f"{path} is missing {exc.args[0]!r} — re-run `ebay-assistant init`"
        ) from None


def load_template() -> str:
    path = config_dir() / TEMPLATE_FILE
    try:
        template = path.read_text().strip()
    except FileNotFoundError:
        raise ConfigError(
            f"no message template found at {path} — run `ebay-assistant init` first"
        ) from None
    if not template:
        raise ConfigError(f"message template {path} is empty")
    return template


def write_secret_file(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    os.chmod(path, 0o600)


def write_config(cfg: Config) -> None:
    content = (
        f'environment = "{cfg.environment}"  # "production" or "sandbox"\n'
        f"days_back = {cfg.days_back}  # how far back to look for labeled orders\n"
        f"email_copy_to_sender = {str(cfg.email_copy_to_sender).lower()}"
        "  # true = eBay emails you a copy of each message\n"
    )
    (cfg.config_dir / CONFIG_FILE).write_text(content)


def write_credentials(creds: Credentials, directory: Path) -> None:
    payload = {
        "app_id": creds.app_id,
        "cert_id": creds.cert_id,
        "refresh_token": creds.refresh_token,
        "refresh_token_expires_at": (
            to_iso(creds.refresh_token_expires_at)
            if creds.refresh_token_expires_at
            else None
        ),
    }
    write_secret_file(directory / CREDENTIALS_FILE, json.dumps(payload, indent=2) + "\n")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_iso(moment: datetime) -> str:
    return (
        moment.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

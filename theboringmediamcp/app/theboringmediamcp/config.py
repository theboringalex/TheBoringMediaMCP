"""Configuration handling for TheBoringMediaMCP.

Precedence (highest first):
  1. values saved from the web UI           -> <DATA_DIR>/config.json
  2. environment variables                  -> TBMM_<SERVICE>_<FIELD>, TBMM_<GENERAL>
  3. Home Assistant add-on options          -> /data/options.json
  4. built-in defaults

Environment variables / add-on options are therefore *start values*; whatever is
saved in the web UI wins afterwards.
"""

import json
import os
import secrets
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

VERSION = "1.0.0"
TOOL_LIMIT_HINT = 100  # many AI clients stop loading tools beyond this number


def _data_dir() -> Path:
    env = os.environ.get("TBMM_DATA_DIR")
    if env:
        return Path(env)
    d = Path("/data")
    if d.is_dir() and os.access(d, os.W_OK):
        return d
    return Path("./data")


DATA_DIR = _data_dir()
CONFIG_FILE = DATA_DIR / "config.json"
OPTIONS_FILE = Path("/data/options.json")


def _f(key: str, label: str, secret: bool = False, placeholder: str = "", help: str = "") -> dict:
    return {"key": key, "label": label, "secret": secret, "placeholder": placeholder, "help": help}


URL = lambda ph: _f("url", "URL", placeholder=ph)  # noqa: E731
APIKEY = lambda help="": _f("api_key", "API-Key", secret=True, help=help)  # noqa: E731

# id -> metadata. The order is the order shown in the UI.
SERVICES: dict[str, dict[str, Any]] = {
    "jellyfin": {
        "title": "Jellyfin", "group": "media", "color": "#00a4dc",
        "desc": "Media server: library, search, sessions, collections, tasks",
        "fields": [URL("http://192.168.1.5:8096"),
                   APIKEY("Jellyfin: Dashboard → API Keys → +")],
    },
    "radarr": {
        "title": "Radarr", "group": "arr", "color": "#ffc230",
        "desc": "Movie management",
        "fields": [URL("http://192.168.1.5:7878"),
                   APIKEY("Radarr: Settings → General → API Key")],
    },
    "sonarr": {
        "title": "Sonarr", "group": "arr", "color": "#35c5f4",
        "desc": "TV series management",
        "fields": [URL("http://192.168.1.5:8989"),
                   APIKEY("Sonarr: Settings → General → API Key")],
    },
    "prowlarr": {
        "title": "Prowlarr", "group": "arr", "color": "#e66000",
        "desc": "Indexer management",
        "fields": [URL("http://192.168.1.5:9696"),
                   APIKEY("Prowlarr: Settings → General → API Key")],
    },
    "seerr": {
        "title": "Seerr", "group": "arr", "color": "#8b5cf6",
        "desc": "Requests (Seerr / Jellyseerr / Overseerr)",
        "fields": [URL("http://192.168.1.5:5055"),
                   APIKEY("Seerr: Settings → General → API Key")],
    },
    "sabnzbd": {
        "title": "SABnzbd", "group": "downloads", "color": "#f5c518",
        "desc": "Usenet downloader (queue, history, speed)",
        "fields": [URL("http://192.168.1.5:8080"),
                   APIKEY("SABnzbd: Config → General → API Key")],
    },
    "gluetun": {
        "title": "Gluetun", "group": "downloads", "color": "#2dd4bf",
        "desc": "VPN container: status, public IP, port forwarding, restart",
        "fields": [URL("http://192.168.1.5:8000"),
                   APIKEY("Only if the control server uses an API key (X-API-Key)"),
                   _f("username", "Username (Basic Auth)", help="Only if the control server uses basic auth"),
                   _f("password", "Password (Basic Auth)", secret=True)],
    },
    "homarr": {
        "title": "Homarr", "group": "dashboard", "color": "#fa5252",
        "desc": "Dashboard: boards, integrations, API",
        "fields": [URL("http://192.168.1.5:7575"),
                   APIKEY("Homarr: Management → Tools → API → create key (id.token)")],
    },
    "jellyfin_collection": {
        "title": "Jellyfin Collection", "group": "media", "color": "#a78bfa",
        "desc": "Collection manager (jfc) – controlled through the Docker API",
        "fields": [_f("url", "Docker endpoint",
                      placeholder="unix:///var/run/docker.sock  or  http://192.168.1.5:2375",
                      help="Docker socket (mounted) or a Docker socket proxy"),
                   _f("container", "Container name", placeholder="jellyfin-collection")],
    },
}

GROUPS = {
    "arr": ["radarr", "sonarr", "prowlarr", "seerr"],
    "downloads": ["sabnzbd", "gluetun"],
    "media": ["jellyfin", "jellyfin_collection"],
}

GENERAL_DEFAULTS = {
    "mcp_token": "",
    "public_url": "",
    "language": "de",
    "max_output_chars": 60000,
    "log_level": "info",
}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on", "ja")


class Config:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stored: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self.load()

    # ---- loading / saving -------------------------------------------------
    def load(self) -> None:
        with self._lock:
            self._stored = {}
            self._options = {}
            try:
                if OPTIONS_FILE.is_file():
                    self._options = json.loads(OPTIONS_FILE.read_text("utf-8"))
            except Exception:
                self._options = {}
            try:
                if CONFIG_FILE.is_file():
                    self._stored = json.loads(CONFIG_FILE.read_text("utf-8"))
            except Exception:
                self._stored = {}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._stored, fh, indent=2, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, CONFIG_FILE)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ---- raw access --------------------------------------------------------
    def _seed(self, key: str) -> Optional[Any]:
        for name in ("TBMM_" + key.upper(), *(("TBMM_TOKEN",) if key == "mcp_token" else ())):
            env = os.environ.get(name)
            if env is not None and env != "":
                if key == "mcp_token" and env.startswith("BITTE-AENDERN"):
                    return None  # unchanged placeholder from the example compose file -> generate a real token
                return env
        v = self._options.get(key)
        if v is not None and v != "":
            return v
        return None

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._stored:
                return self._stored[key]
            seed = self._seed(key)
            if seed is not None:
                return seed
            return GENERAL_DEFAULTS.get(key, default) if default is None else default

    def set_many(self, values: dict[str, Any]) -> None:
        with self._lock:
            for k, v in values.items():
                self._stored[k] = v
            self._save()

    # ---- typed helpers -----------------------------------------------------
    def general(self, key: str) -> Any:
        return self.get(key, GENERAL_DEFAULTS.get(key))

    def max_chars(self) -> int:
        try:
            return max(2000, int(self.general("max_output_chars")))
        except Exception:
            return 60000

    def service(self, name: str) -> dict[str, Any]:
        meta = SERVICES[name]
        en = self.get(f"{name}_enabled", None)
        url_set = bool(str(self.get(f"{name}_url", "") or "").strip())
        out: dict[str, Any] = {
            "enabled": url_set if en is None else _truthy(en),
            "read_only": _truthy(self.get(f"{name}_read_only", False)),
            "verify_ssl": _truthy(self.get(f"{name}_verify_ssl", True)),
        }
        for fld in meta["fields"]:
            out[fld["key"]] = str(self.get(f"{name}_{fld['key']}", "") or "")
        return out

    def enabled_services(self) -> list[str]:
        return [n for n in SERVICES if self.service(n)["enabled"]]

    def ensure_token(self) -> str:
        tok = str(self.general("mcp_token") or "")
        if not tok:
            tok = secrets.token_urlsafe(32)
            self.set_many({"mcp_token": tok})
        return tok

    def regenerate_token(self) -> str:
        tok = secrets.token_urlsafe(32)
        self.set_many({"mcp_token": tok})
        return tok


CONFIG = Config()

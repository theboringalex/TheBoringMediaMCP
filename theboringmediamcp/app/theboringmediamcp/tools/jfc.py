"""Jellyfin Collection (jfc) tools.

jfc (github.com/4lx69/jellyfin-collection) is a CLI/scheduler container without an
HTTP API. It is therefore controlled through the Docker Engine API: `docker exec`
into the container and read its logs. Point the "Docker endpoint" at the mounted
socket (unix:///var/run/docker.sock) or at a Docker socket proxy (http://host:2375).
"""

import base64
import posixpath
import re
import shlex
from typing import Any, Optional

import httpx

from ..config import CONFIG
from ..core import ServiceError, ping, tool

S = "jellyfin_collection"
DEFAULT_CONTAINER = "jellyfin-collection"
CONFIG_ROOT = "/config"
_SECRET_LINE = re.compile(r"(?im)^(\s*[\w.-]*(?:api_?key|token|secret|passw(?:or)?d|client_id|client_secret)[\w.-]*\s*[:=]\s*)(\S.*)$")


def _client(cfg: dict, timeout: float) -> tuple[httpx.AsyncClient, str]:
    url = (cfg.get("url") or "unix:///var/run/docker.sock").strip()
    if url.startswith("unix://"):
        return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=url[len("unix://"):]),
                                 base_url="http://docker", timeout=timeout), "http://docker"
    url = url.replace("tcp://", "http://").rstrip("/")
    if not url.startswith("http"):
        url = "http://" + url
    return httpx.AsyncClient(base_url=url, timeout=timeout), url


def _name(cfg: dict) -> str:
    return (cfg.get("container") or DEFAULT_CONTAINER).strip()


async def _docker(cfg: dict, method: str, path: str, *, timeout: float = 30, **kw) -> httpx.Response:
    cl, _ = _client(cfg, timeout)
    try:
        async with cl:
            r = await cl.request(method, path, **kw)
    except httpx.ConnectError as e:
        raise ServiceError(f"Cannot reach the Docker endpoint ({e}). Mount /var/run/docker.sock or use a socket proxy.")
    except httpx.TimeoutException:
        raise ServiceError(f"Docker request timed out after {timeout:.0f}s")
    if r.status_code == 404:
        raise ServiceError(f"Container '{_name(cfg)}' not found (HTTP 404).")
    if r.status_code >= 400:
        raise ServiceError(f"Docker API HTTP {r.status_code}: {r.text[:300]}")
    return r


async def _exec(cfg: dict, cmd: list[str], *, detach: bool = False, timeout: float = 120) -> dict:
    c = _name(cfg)
    cl, _ = _client(cfg, timeout + 10)
    try:
        async with cl:
            r = await cl.post(f"/containers/{c}/exec", json={
                "AttachStdout": not detach, "AttachStderr": not detach, "Tty": True, "Cmd": cmd})
            if r.status_code == 404:
                raise ServiceError(f"Container '{c}' not found.")
            if r.status_code == 409:
                raise ServiceError(f"Container '{c}' is not running.")
            if r.status_code >= 400:
                raise ServiceError(f"Docker exec create failed: HTTP {r.status_code} {r.text[:300]}")
            eid = r.json()["Id"]
            try:
                s = await cl.post(f"/exec/{eid}/start", json={"Detach": detach, "Tty": True}, timeout=timeout)
            except httpx.TimeoutException:
                return {"exit_code": None, "output": f"(still running after {timeout:.0f}s — use jfc_logs to follow)"}
            info = (await cl.get(f"/exec/{eid}/json")).json()
            return {"exit_code": info.get("ExitCode"), "running": info.get("Running"),
                    "output": s.text[-12000:] if not detach else ""}
    except httpx.ConnectError as e:
        raise ServiceError(f"Cannot reach the Docker endpoint ({e}).")


def _cfg() -> dict:
    return CONFIG.service(S)


@ping(S)
async def _ping(cfg: dict) -> dict:
    r = await _docker(cfg, "GET", f"/containers/{_name(cfg)}/json", timeout=15)
    st = r.json().get("State", {})
    if not st.get("Running"):
        raise ServiceError(f"Container '{_name(cfg)}' exists but is {st.get('Status')}.")
    return {"version": None, "detail": f"container {_name(cfg)} running · {r.json().get('Config', {}).get('Image')}"}


@tool(S)
async def jfc_status() -> Any:
    """State of the jellyfin-collection container (running, uptime, image, health) plus the last log lines."""
    cfg = _cfg()
    j = (await _docker(cfg, "GET", f"/containers/{_name(cfg)}/json")).json()
    st = j.get("State", {})
    return {"container": _name(cfg), "status": st.get("Status"), "running": st.get("Running"),
            "started_at": st.get("StartedAt"), "health": (st.get("Health") or {}).get("Status"),
            "image": (j.get("Config") or {}).get("Image"),
            "last_logs": (await _logs(cfg, 8)).splitlines()}


async def _logs(cfg: dict, tail: int) -> str:
    c = _name(cfg)
    j = (await _docker(cfg, "GET", f"/containers/{c}/json")).json()
    tty = (j.get("Config") or {}).get("Tty", False)
    r = await _docker(cfg, "GET", f"/containers/{c}/logs", params={
        "stdout": 1, "stderr": 1, "tail": max(1, min(tail, 2000)), "timestamps": 0})
    raw = r.content
    if tty:
        return raw.decode("utf-8", "replace")
    out, i = [], 0
    while i + 8 <= len(raw):  # multiplexed stream: 8-byte header per frame
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out.append(raw[i + 8:i + 8 + size].decode("utf-8", "replace"))
        i += 8 + size
    return "".join(out)


@tool(S)
async def jfc_logs(tail: int = 100) -> Any:
    """Last log lines of the jellyfin-collection container (also shows output of jfc_run)."""
    return (await _logs(_cfg(), tail))[-20000:]


@tool(S, "write")
async def jfc_run(library: Optional[str] = None, collection: Optional[str] = None, dry_run: bool = False,
                  force_posters: bool = False, wait_seconds: int = 0) -> Any:
    """Run the collection sync now (`jfc run`). Optionally for one library / collection, as dry run, or with forced poster regeneration. wait_seconds=0 starts it in the background (follow with jfc_logs); >0 waits up to that long and returns the output."""
    args = ["jfc", "run"]
    if library:
        args += ["--library", library]
    if collection:
        args += ["--collection", collection]
    if dry_run:
        args.append("--dry-run")
    if force_posters:
        args.append("--force-posters")
    return await _run(args, wait_seconds)


async def _run(args: list[str], wait_seconds: int) -> dict:
    cfg = _cfg()
    if wait_seconds and wait_seconds > 0:
        res = await _exec(cfg, args, timeout=min(wait_seconds, 900))
        return {"command": " ".join(args), **res}
    line = " ".join(shlex.quote(a) for a in args) + " > /proc/1/fd/1 2>&1"
    await _exec(cfg, ["sh", "-c", line], detach=True)
    return {"command": " ".join(args), "started": True, "hint": "Running in the background. Use jfc_logs to follow the output."}


@tool(S)
async def jfc_validate() -> Any:
    """Validate the jfc configuration (`jfc validate`)."""
    return {"command": "jfc validate", **await _exec(_cfg(), ["jfc", "validate"], timeout=120)}


@tool(S)
async def jfc_list_collections() -> Any:
    """List the collections jfc manages (`jfc list-collections`)."""
    return {"command": "jfc list-collections", **await _exec(_cfg(), ["jfc", "list-collections"], timeout=120)}


@tool(S)
async def jfc_test_connections() -> Any:
    """Test jfc's connections to Jellyfin, TMDb, Radarr, Sonarr, Trakt, OpenAI (`jfc test-connections`)."""
    return {"command": "jfc test-connections", **await _exec(_cfg(), ["jfc", "test-connections"], timeout=120)}


@tool(S, "write")
async def jfc_generate_poster(collection: str, category: str, library: str, wait_seconds: int = 0) -> Any:
    """Generate an AI poster for a collection (`jfc generate-poster "<collection>" --category X --library Y`). Uses the OpenAI key configured in jfc."""
    return await _run(["jfc", "generate-poster", collection, "--category", category, "--library", library], wait_seconds)


@tool(S, "write")
async def jfc_exec(args: str, wait_seconds: int = 60) -> Any:
    """Run any other `jfc` subcommand, e.g. args='run --dry-run'. Only the jfc binary can be run; wait_seconds=0 = background."""
    parts = shlex.split(args)
    if parts and parts[0] == "jfc":
        parts = parts[1:]
    if not parts:
        raise ServiceError("Give the jfc arguments, e.g. 'validate'.")
    return await _run(["jfc", *parts], wait_seconds)


@tool(S, "destructive")
async def jfc_restart_container() -> Any:
    """Restart the jellyfin-collection container (restarts the scheduler)."""
    cfg = _cfg()
    await _docker(cfg, "POST", f"/containers/{_name(cfg)}/restart", timeout=60)
    return {"restarted": _name(cfg)}


def _safe_path(path: str) -> str:
    p = posixpath.normpath(path if path.startswith("/") else f"{CONFIG_ROOT}/{path}")
    if not (p == CONFIG_ROOT or p.startswith(CONFIG_ROOT + "/")):
        raise ServiceError(f"Only files below {CONFIG_ROOT} can be accessed.")
    return p


@tool(S)
async def jfc_list_config_files() -> Any:
    """List the files in jfc's /config folder (config.yml and the collection YAML files)."""
    res = await _exec(_cfg(), ["find", CONFIG_ROOT, "-type", "f", "-not", "-path", f"{CONFIG_ROOT}/cache/*",
                               "-not", "-name", "*.jpg", "-not", "-name", "*.png"], timeout=30)
    return res["output"].replace("\r", "").splitlines()


@tool(S)
async def jfc_read_config_file(path: str) -> Any:
    """Read a text file below /config (e.g. config.yml or a collection YAML). Values of keys named *key/*token/*secret/*password are masked."""
    p = _safe_path(path)
    res = await _exec(_cfg(), ["cat", p], timeout=30)
    if res.get("exit_code") not in (0, None):
        raise ServiceError(f"Could not read {p}: {res['output'][:200]}")
    return _SECRET_LINE.sub(r"\1***", res["output"].replace("\r\n", "\n"))


@tool(S, "write")
async def jfc_write_config_file(path: str, content: str) -> Any:
    """Write a text file below /config (e.g. a collection YAML). The previous version is kept as '<name>.bak'. Masked values ('***') are never written back: do not overwrite config.yml with content obtained from jfc_read_config_file."""
    p = _safe_path(path)
    if "***" in content and p.endswith((".yml", ".yaml")) and posixpath.basename(p) == "config.yml":
        raise ServiceError("Refusing to write config.yml containing masked '***' values (would destroy your keys).")
    b64 = base64.b64encode(content.encode("utf-8")).decode()
    script = f'[ -f {shlex.quote(p)} ] && cp {shlex.quote(p)} {shlex.quote(p + ".bak")}; ' \
             f'mkdir -p "$(dirname {shlex.quote(p)})" && echo {b64} | base64 -d > {shlex.quote(p)}'
    res = await _exec(_cfg(), ["sh", "-c", script], timeout=30)
    if res.get("exit_code") not in (0, None):
        raise ServiceError(f"Write failed: {res['output'][:200]}")
    return {"written": p, "bytes": len(content.encode()), "backup": p + ".bak"}

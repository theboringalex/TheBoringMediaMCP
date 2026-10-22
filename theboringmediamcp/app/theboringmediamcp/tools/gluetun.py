"""Gluetun tools (control server API)."""

import asyncio
from typing import Any, Optional

from ..core import ServiceError, call, generic, ping, redact, tool

S = "gluetun"


async def _try(*paths: str) -> Any:
    """Newer Gluetun versions use /v1/vpn/*, older ones /v1/openvpn/*."""
    last: Optional[Exception] = None
    for p in paths:
        try:
            return await call(S, "GET", p, timeout=15)
        except ServiceError as e:
            last = e
            if "HTTP 404" not in str(e):
                raise
    raise last or ServiceError("gluetun: endpoint not found")


@ping(S)
async def _ping(cfg: dict) -> dict:
    ip = await call(S, "GET", "/v1/publicip/ip", cfg_override=cfg, timeout=15)
    where = ", ".join(x for x in (ip.get("city"), ip.get("country")) if x)
    return {"version": None, "detail": f"public IP {ip.get('public_ip')} ({where})"}


@tool(S)
async def gluetun_status() -> Any:
    """Everything at a glance: VPN state, public IP and location, forwarded port, DNS state."""
    out: dict = {}
    for key, paths in (("vpn", ("/v1/vpn/status", "/v1/openvpn/status")),
                       ("public_ip", ("/v1/publicip/ip",)),
                       ("forwarded_port", ("/v1/portforward", "/v1/openvpn/portforwarded")),
                       ("dns", ("/v1/dns/status",))):
        try:
            out[key] = await _try(*paths)
        except ServiceError as e:
            out[key] = {"unavailable": str(e)[:160]}
    return out


@tool(S)
async def gluetun_public_ip() -> Any:
    """Public IP address as seen from the internet, with country/city/provider."""
    return await call(S, "GET", "/v1/publicip/ip", timeout=20)


@tool(S)
async def gluetun_vpn_status() -> Any:
    """VPN state: running | stopped | crashed."""
    return await _try("/v1/vpn/status", "/v1/openvpn/status")


@tool(S, "destructive")
async def gluetun_set_vpn_status(status: str) -> Any:
    """Start or stop the VPN tunnel (status = 'running' | 'stopped'). While stopped, containers behind Gluetun have no internet (kill switch)."""
    if status not in ("running", "stopped"):
        raise ServiceError("status must be 'running' or 'stopped'")
    try:
        return await call(S, "PUT", "/v1/vpn/status", body={"status": status})
    except ServiceError as e:
        if "HTTP 404" not in str(e):
            raise
        return await call(S, "PUT", "/v1/openvpn/status", body={"status": status})


@tool(S, "destructive")
async def gluetun_restart_vpn() -> Any:
    """Restart the VPN tunnel (stop → start) to get a new server/IP. Waits until the tunnel is up and reports the new public IP."""
    await gluetun_set_vpn_status.__wrapped__("stopped")
    await asyncio.sleep(2)
    await gluetun_set_vpn_status.__wrapped__("running")
    state: Any = None
    for _ in range(20):
        await asyncio.sleep(3)
        try:
            state = await _try("/v1/vpn/status", "/v1/openvpn/status")
            if (state or {}).get("status") == "running":
                break
        except ServiceError:
            continue
    ip: Any
    try:
        ip = await call(S, "GET", "/v1/publicip/ip", timeout=20)
    except ServiceError as e:
        ip = {"unavailable": str(e)[:160]}
    return {"vpn": state, "public_ip": ip}


@tool(S)
async def gluetun_forwarded_port() -> Any:
    """Port opened by VPN port forwarding (if the provider supports it)."""
    return await _try("/v1/portforward", "/v1/openvpn/portforwarded")


@tool(S)
async def gluetun_dns_status() -> Any:
    """State of Gluetun's DNS-over-TLS resolver."""
    return await call(S, "GET", "/v1/dns/status")


@tool(S)
async def gluetun_vpn_settings() -> Any:
    """Active VPN settings (provider, server selection, protocol). Keys and passwords are masked."""
    return redact(await _try("/v1/vpn/settings", "/v1/openvpn/settings"))


@tool(S, "write", mixed=True)
async def gluetun_api_request(method: str, path: str, query: Optional[dict] = None, body: Optional[Any] = None) -> Any:
    """Raw Gluetun control-server request. path starts with '/', e.g. '/v1/updater/status'. GET only in read-only mode."""
    return await generic(S, method, path, query, body)

# Changelog

## 1.0.0 – 2026-10-22
First release.
- MCP server (Streamable HTTP on `/mcp`, legacy SSE on `/sse`, stdio via `--stdio`)
- 136 tools for Jellyfin, Radarr, Sonarr, Prowlarr, Seerr, SABnzbd, Gluetun, Homarr and Jellyfin Collection
- Split endpoints per service / group (`/mcp/arr`, `/mcp/downloads`, `/mcp/media`, `/mcp/<service>`) to stay below client tool limits
- Web UI (German / English): status, settings, connection snippets, tool list, call log
- Per-service on/off switch, read-only mode, TLS verification switch
- Bearer token, `?token=` and secret-path (`/s/<token>/mcp`) authentication
- Home Assistant add-on with Ingress and Docker image

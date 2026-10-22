"""Entry point:  python -m theboringmediamcp [--stdio] [--host H] [--port P]"""

import argparse
import logging
import os

from .config import CONFIG, VERSION


def main() -> None:
    ap = argparse.ArgumentParser(prog="theboringmediamcp", description="TheBoringMediaMCP – MCP server for Jellyfin & the *arr stack")
    ap.add_argument("--stdio", action="store_true", help="speak MCP over stdin/stdout (for local clients such as Claude Desktop)")
    ap.add_argument("--host", default=os.environ.get("TBMM_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("TBMM_PORT", "17830")))
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args()
    if args.version:
        print(VERSION)
        return

    level = str(CONFIG.general("log_level") or "info").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    for noisy in ("mcp", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING if level != "DEBUG" else logging.DEBUG)

    if args.stdio:
        from .server import build_mcp
        build_mcp("all").run("stdio")
        return

    import uvicorn
    from .server import create_app

    logging.getLogger("theboringmediamcp").info(
        "TheBoringMediaMCP %s listening on http://%s:%s  (UI: /, MCP: /mcp, legacy SSE: /sse)",
        VERSION, args.host, args.port)
    uvicorn.run(create_app(args.host, args.port), host=args.host, port=args.port,
                log_level="warning" if level != "DEBUG" else "debug",
                proxy_headers=False)  # never trust X-Forwarded-For: the Ingress check relies on the real peer address


if __name__ == "__main__":
    main()

"""Production entry point: uvicorn on one dual-stack socket.

Railway's private network is IPv6 (the web app reaches the API at
<service>.railway.internal), while its public edge and health checks may use
IPv4. Uvicorn binds a single host, so this opens one IPv6 socket that also
accepts IPv4 and hands it over."""

import socket

import uvicorn

from config import settings


def main() -> None:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", settings.port))
    sock.listen(2048)
    uvicorn.run("app.main:app", fd=sock.fileno(), proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()

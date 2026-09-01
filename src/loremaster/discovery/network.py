"""Discovering the LAN IP address that the tablet should hit."""

from __future__ import annotations

import socket


def get_lan_ip() -> str:
    """Best-effort local IP address usable from another machine on the same
    network. Uses the "connect to a routable address" trick so the OS picks
    the interface with a default route — no packets are actually sent because
    UDP.connect doesn't send anything.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

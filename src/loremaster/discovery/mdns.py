"""Register the Loremaster HTTP server on the local network via mDNS.

After registration, `loremaster.local:PORT` should resolve from any device on
the same network with mDNS support (macOS, iOS, most Linux distros, Android
via Chrome for _http._tcp discovery).

Uses AsyncZeroconf so registration integrates with the FastAPI event loop —
the sync Zeroconf API blocks its own internal loop when called from inside
another asyncio loop.
"""

from __future__ import annotations

import logging
import socket

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

log = logging.getLogger(__name__)

_SERVICE_TYPE = "_http._tcp.local."
_SERVICE_NAME = "Loremaster._http._tcp.local."
_HOSTNAME = "loremaster.local."


class MDNSRegistration:
    def __init__(self, port: int, lan_ip: str) -> None:
        self.port = port
        self.lan_ip = lan_ip
        self._azc: AsyncZeroconf | None = None
        self._info: ServiceInfo | None = None

    async def register(self) -> None:
        try:
            self._azc = AsyncZeroconf()
            self._info = ServiceInfo(
                _SERVICE_TYPE,
                _SERVICE_NAME,
                addresses=[socket.inet_aton(self.lan_ip)],
                port=self.port,
                properties={"path": "/", "app": "loremaster"},
                server=_HOSTNAME,
            )
            await self._azc.async_register_service(self._info)
            log.info("mDNS: registered http://%s:%d (also http://%s:%d)",
                     _HOSTNAME.rstrip("."), self.port, self.lan_ip, self.port)
        except Exception:  # noqa: BLE001
            # mDNS is convenience; failure (port 5353 blocked, other daemon
            # already running, no multicast) should not stop the app.
            log.exception("mDNS registration failed — falling back to IP-only access")
            if self._azc is not None:
                try:
                    await self._azc.async_close()
                except Exception:  # noqa: BLE001
                    pass
            self._azc = None
            self._info = None

    async def unregister(self) -> None:
        if self._azc is None:
            return
        try:
            if self._info is not None:
                await self._azc.async_unregister_service(self._info)
        except Exception:  # noqa: BLE001
            log.exception("mDNS unregister failed")
        finally:
            await self._azc.async_close()
            self._azc = None
            self._info = None

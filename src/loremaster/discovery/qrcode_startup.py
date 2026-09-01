"""Show a friendly QR code + URLs in the terminal at startup.

Uses the `qrcode` library's ASCII renderer — no image dependency needed.
"""

from __future__ import annotations

import qrcode


def print_startup_banner(lan_ip: str, port: int, hostname: str = "loremaster.local") -> None:
    lan_url = f"http://{lan_ip}:{port}"
    mdns_url = f"http://{hostname}:{port}"

    qr = qrcode.QRCode(border=1)
    qr.add_data(lan_url)
    qr.make(fit=True)

    banner_lines = [
        "",
        "═══════════════════════════════════════════════",
        "  Loremaster está pronto",
        "═══════════════════════════════════════════════",
        f"  Tablet (mesma WiFi):  {lan_url}",
        f"  Também disponível em: {mdns_url}",
        f"  Notebook:             http://127.0.0.1:{port}",
        f"  Mapa de campanha:     {lan_url}/map",
        "",
        "  Escaneie o QR code abaixo no tablet para abrir:",
        "",
    ]
    for line in banner_lines:
        print(line)
    qr.print_ascii(invert=True)
    print()

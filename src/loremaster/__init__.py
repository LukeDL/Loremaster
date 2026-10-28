"""Loremaster — audio companion for D&D sessions.

Keep package import side-effect free so data, event, and mixer modules remain
usable on machines where PortAudio is not installed.
"""


def main() -> None:
    """Console-script shim that imports the app only when executed."""
    from loremaster.main import main as run_main

    run_main()

__all__ = ["main"]

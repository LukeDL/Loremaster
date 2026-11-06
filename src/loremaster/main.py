"""FastAPI app entrypoint: wires DB + audio engine + event bus + REST + WS."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from loremaster.api import auth, campaigns, characters, playback, scenes, uploads, users
from loremaster.api.deps import get_auth_context
from loremaster.api.ws import WsBroadcaster, router as ws_router
from loremaster.audio.engine import AudioEngine
from loremaster.audio.loader import AudioLoader
from loremaster.audio.scene_player import ScenePlayer
from loremaster.config import settings
from loremaster.discovery.mdns import MDNSRegistration
from loremaster.discovery.network import get_lan_ip
from loremaster.discovery.qrcode_startup import print_startup_banner
from loremaster.events import EventBus
from loremaster.models.db import Database
from loremaster.scene_service import SceneService

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    db = Database(settings.db_url)
    await db.create_all()

    bus = EventBus()
    engine = AudioEngine(
        sample_rate=settings.sample_rate,
        block_size=settings.block_size,
        device=settings.audio_device,
    )
    loader = AudioLoader(target_sample_rate=settings.sample_rate)
    player = ScenePlayer(engine)
    service = SceneService(
        engine=engine,
        loader=loader,
        player=player,
        db=db,
        bus=bus,
        audio_dir=settings.audio_dir,
    )
    await service.validate_references()
    broadcaster = WsBroadcaster(bus, service)

    engine.start()
    broadcaster.start()

    lan_ip = get_lan_ip()
    mdns = MDNSRegistration(port=settings.port, lan_ip=lan_ip)
    await mdns.register()

    app.state.db = db
    app.state.bus = bus
    app.state.engine = engine
    app.state.scene_service = service
    app.state.ws_broadcaster = broadcaster
    app.state.mdns = mdns

    log.info("loremaster ready on http://%s:%d", settings.host, settings.port)
    print_startup_banner(lan_ip=lan_ip, port=settings.port)

    try:
        yield
    finally:
        await mdns.unregister()
        await broadcaster.stop()
        engine.stop()
        await db.close()


def create_app(lifespan_context=lifespan) -> FastAPI:
    """Build the app with an explicit seam for hardware-free tests."""
    app = FastAPI(title="Loremaster", version="0.1.0", lifespan=lifespan_context)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(campaigns.router)
    app.include_router(characters.player_router)
    app.include_router(characters.admin_router)
    app.include_router(uploads.router)
    app.include_router(scenes.router)
    app.include_router(scenes.singletons_router)
    app.include_router(playback.router)
    app.include_router(ws_router)

    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        async def authenticated_page(request: Request, filename: str):
            context = await get_auth_context(request)
            if context is None:
                return RedirectResponse("/login", status_code=303)
            if context.user.role != "gm":
                return RedirectResponse("/player", status_code=303)
            return FileResponse(web_dir / filename)

        @app.get("/login", include_in_schema=False)
        async def login_page(request: Request):
            context = await get_auth_context(request)
            if context is not None:
                destination = "/" if context.user.role == "gm" else "/player"
                return RedirectResponse(destination, status_code=303)
            return FileResponse(web_dir / "login.html")

        @app.get("/player", include_in_schema=False)
        async def player_page(request: Request):
            context = await get_auth_context(request)
            if context is None:
                return RedirectResponse("/login", status_code=303)
            if context.user.role == "gm":
                return RedirectResponse("/", status_code=303)
            return FileResponse(web_dir / "player.html")

        @app.get("/", include_in_schema=False)
        @app.get("/index.html", include_in_schema=False)
        async def index_page(request: Request):
            return await authenticated_page(request, "index.html")

        @app.get("/map", include_in_schema=False)
        @app.get("/map.html", include_in_schema=False)
        async def map_page(request: Request):
            return await authenticated_page(request, "map.html")

        @app.get("/users", include_in_schema=False)
        @app.get("/users.html", include_in_schema=False)
        async def users_page(request: Request):
            return await authenticated_page(request, "users.html")

        @app.get("/campaigns", include_in_schema=False)
        @app.get("/campaigns.html", include_in_schema=False)
        async def campaigns_page(request: Request):
            return await authenticated_page(request, "campaigns.html")

        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "loremaster.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()

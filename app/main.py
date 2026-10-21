from __future__ import annotations

import asyncio
import contextlib
import os

from fastapi import FastAPI

from app.api import build_router
from app.config import Settings
from app.db import build_session_factory


async def run_polling(settings: Settings) -> None:
    """Run the aiogram polling loop using short-lived database sessions."""
    from app.bot import create_bot, create_dispatcher

    bot = create_bot(settings)
    dispatcher = create_dispatcher(build_session_factory(settings.database_url), settings)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    supplied_settings = settings is not None
    resolved = settings or Settings.from_env()
    application = FastAPI(title="QR Omissions", version="0.1.0")
    application.include_router(build_router(resolved))

    # The bot is started as an application lifespan task when explicitly enabled.
    # Keeping this opt-in makes API tests and migrations independent from Telegram.
    # An explicitly injected Settings object is primarily used by API tests and
    # local integrations; keep those app instances API-only unless enabled.
    bot_flag = os.getenv("RUN_TELEGRAM_BOT", "0" if supplied_settings else "1")
    if bot_flag.lower() in {"1", "true", "yes"}:
        @application.on_event("startup")
        async def start_bot() -> None:
            try:
                run_polling_func = run_polling
            except (ImportError, AttributeError):
                return
            application.state.bot_task = asyncio.create_task(run_polling_func(resolved))

        @application.on_event("shutdown")
        async def stop_bot() -> None:
            task = getattr(application.state, "bot_task", None)
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return application


def _build_default_app() -> FastAPI:
    """Build the production app while keeping module imports test-friendly."""
    if os.getenv("DATABASE_URL"):
        return create_app()

    application = FastAPI(title="QR Omissions", version="0.1.0")

    @application.get("/health")
    def unavailable_health() -> dict[str, str]:
        return {"status": "configuration_required"}

    return application


app = _build_default_app()

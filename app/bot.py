from __future__ import annotations

"""Telegram bot handlers for guests and event organizers."""

import inspect
import io
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.qr import decode_qr_bytes, generate_qr_png
from app.security.authorization import is_organizer
from app.security.tokens import InvalidToken, issue_token


class BonusStates(StatesGroup):
    """States used while an organizer enters a manual bonus."""

    waiting_amount = State()
    waiting_reason = State()


def _setting(settings: Any, name: str, default: Any = None) -> Any:
    return getattr(settings, name, default)


def _organizer(settings: Any, telegram_id: int | None) -> bool:
    return telegram_id is not None and is_organizer(
        telegram_id, frozenset(_setting(settings, "organizer_telegram_ids", ()))
    )


@contextmanager
def _service_context(session_factory: Callable[[], Any], settings: Any):
    """Create the per-update GuestService without retaining a DB session globally."""
    session = session_factory()
    try:
        try:
            from app.services import GuestService
        except ImportError:
            from app.services.guest_service import GuestService
        service = GuestService(
            session,
            token_secret=_setting(settings, "token_secret"),
            checkin_points=_setting(settings, "checkin_points", 10),
            bonus_min_points=_setting(settings, "bonus_min_points", 1),
            bonus_max_points=_setting(settings, "bonus_max_points", 100),
        )
        yield service
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def _call(service: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
    result = getattr(service, method_name)(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _value(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]
        return default
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def _card_guest(card: Any) -> Any:
    return _value(card, "guest", default=card)


def _card_guest_id(card: Any) -> str | None:
    guest = _card_guest(card)
    value = _value(card, "guest_id", default=None) or _value(guest, "id", default=None)
    return str(value) if value is not None else None


def _card_points(card: Any) -> int:
    value = _value(card, "total_points", "points", "balance", default=0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _card_checked_in(card: Any) -> bool:
    value = _value(card, "checked_in", "is_checked_in", "checkin", "check_in", default=False)
    return bool(value)


def _render_card(card: Any) -> str:
    guest = _card_guest(card)
    name = _value(card, "name", default=None) or _value(guest, "name", default="Гость")
    category = _value(card, "category", default=None) or _value(guest, "category", default="—")
    status = "уже отмечен" if _card_checked_in(card) else "не отмечен"
    return (
        f"<b>{name}</b>\n"
        f"Категория: {category}\n"
        f"Баллы: {_card_points(card)}\n"
        f"Статус check-in: {status}"
    )


def _card_keyboard(card: Any) -> InlineKeyboardMarkup:
    guest_id = _card_guest_id(card) or ""
    checked = _card_checked_in(card)
    checkin_text = "✅ Check-in выполнен" if checked else "✅ Выполнить check-in"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=checkin_text, callback_data=f"checkin:{guest_id}")],
            [InlineKeyboardButton(text="➕ Добавить бонус", callback_data=f"bonus:{guest_id}")],
        ]
    )


def _guest_token(guest: Any, secret: str) -> str:
    guest_id = _value(guest, "id")
    nonce = _value(guest, "token_nonce", "nonce")
    if guest_id is None or nonce is None:
        raise ValueError("guest has no token identity")
    return issue_token(str(guest_id), str(nonce), secret)


async def _send_card(message: Message, card: Any) -> None:
    await message.answer(_render_card(card), reply_markup=_card_keyboard(card), parse_mode=ParseMode.HTML)


def _install_handlers(router: Router, session_factory: Callable[[], Any], settings: Any) -> Router:
    @router.message(Command("start"))
    async def start_handler(message: Message) -> None:
        if _organizer(settings, message.from_user.id if message.from_user else None):
            await message.answer("Вы организатор. Отправьте фото QR-кода или вставьте токен текстом.")
        else:
            await message.answer("Добро пожаловать! Используйте /qr, чтобы получить свой QR-код.")

    @router.message(Command("qr"))
    async def qr_handler(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        with _service_context(session_factory, settings) as service:
            guest = await _call(service, "get_guest_by_telegram_id", user.id)
        if guest is None:
            await message.answer("Гость с вашим Telegram ID не найден. Обратитесь к администратору.")
            return
        try:
            token = _guest_token(guest, _setting(settings, "token_secret", ""))
            image = generate_qr_png(token)
        except (TypeError, ValueError, RuntimeError):
            await message.answer("Не удалось сформировать QR-код. Обратитесь к администратору.")
            return
        await message.answer_photo(
            BufferedInputFile(image, filename="guest-qr.png"),
            caption="Ваш QR-код для регистрации на мероприятии.",
        )

    async def process_token(message: Message, token: str) -> None:
        user = message.from_user
        if user is None or not _organizer(settings, user.id):
            await message.answer("Эта операция доступна только организаторам.")
            return
        try:
            with _service_context(session_factory, settings) as service:
                card = await _call(service, "get_card_by_token", token.strip())
        except (InvalidToken, ValueError, LookupError):
            card = None
        if card is None:
            await message.answer("QR-токен недействителен или гость не найден.")
            return
        await _send_card(message, card)

    @router.message(F.photo)
    async def photo_handler(message: Message) -> None:
        user = message.from_user
        if user is None or not _organizer(settings, user.id):
            await message.answer("Сканирование QR доступно только организаторам.")
            return
        photo = message.photo[-1]
        buffer = io.BytesIO()
        try:
            await message.bot.download(photo.file_id, destination=buffer)
            token = decode_qr_bytes(buffer.getvalue())
        except Exception:
            token = None
        if not token:
            await message.answer("Не удалось распознать QR. Отправьте фото чётче или вставьте токен текстом.")
            return
        await process_token(message, token)

    @router.message(BonusStates.waiting_amount)
    async def bonus_amount_handler(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            amount = int(raw)
        except ValueError:
            await message.answer("Введите целое число баллов.")
            return
        lower = int(_setting(settings, "bonus_min_points", 1))
        upper = int(_setting(settings, "bonus_max_points", 100))
        if not lower <= amount <= upper:
            await message.answer(f"Сумма должна быть от {lower} до {upper} баллов.")
            return
        await state.update_data(amount=amount)
        await state.set_state(BonusStates.waiting_reason)
        await message.answer("Введите причину начисления бонуса:")

    @router.message(BonusStates.waiting_reason)
    async def bonus_reason_handler(message: Message, state: FSMContext) -> None:
        reason = (message.text or "").strip()
        if not reason:
            await message.answer("Причина не должна быть пустой.")
            return
        data = await state.get_data()
        guest_id = data.get("guest_id")
        user = message.from_user
        if not guest_id or user is None or not _organizer(settings, user.id):
            await state.clear()
            await message.answer("Сессия бонуса недействительна.")
            return
        try:
            with _service_context(session_factory, settings) as service:
                await _call(service, "add_bonus", guest_id, user.id, int(data["amount"]), reason)
                card = await _call(service, "get_card_by_guest_id", guest_id)
        except (LookupError, ValueError):
            await state.clear()
            await message.answer("Не удалось начислить бонус: проверьте гостя и сумму.")
            return
        await state.clear()
        await message.answer("Бонус начислен.")
        if card is not None:
            await _send_card(message, card)

    @router.callback_query(F.data.startswith("checkin:"))
    async def checkin_callback(callback: CallbackQuery) -> None:
        user = callback.from_user
        guest_id = (callback.data or "").split(":", 1)[1]
        if not _organizer(settings, user.id):
            await callback.answer("Недоступно", show_alert=True)
            return
        try:
            with _service_context(session_factory, settings) as service:
                result = await _call(service, "check_in", guest_id, user.id)
                idempotent = bool(_value(result, "idempotent", default=False))
                card = _value(result, "card", default=None) or await _call(service, "get_card_by_guest_id", guest_id)
        except (LookupError, ValueError):
            await callback.answer("Гость не найден.", show_alert=True)
            return
        await callback.answer("Check-in уже был выполнен." if idempotent else "Check-in выполнен.")
        if callback.message and card is not None:
            await callback.message.edit_text(_render_card(card), reply_markup=_card_keyboard(card), parse_mode=ParseMode.HTML)

    @router.callback_query(F.data.startswith("bonus:"))
    async def bonus_callback(callback: CallbackQuery, state: FSMContext) -> None:
        user = callback.from_user
        guest_id = (callback.data or "").split(":", 1)[1]
        if not _organizer(settings, user.id):
            await callback.answer("Недоступно", show_alert=True)
            return
        await state.update_data(guest_id=guest_id)
        await state.set_state(BonusStates.waiting_amount)
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                f"Введите сумму бонуса от {_setting(settings, 'bonus_min_points', 1)} "
                f"до {_setting(settings, 'bonus_max_points', 100)} баллов:"
            )

    @router.message(F.text)
    async def token_text_handler(message: Message) -> None:
        text = (message.text or "").strip()
        if text.startswith("qr1."):
            await process_token(message, text)

    return router


def create_dispatcher(session_factory: Callable[[], Any], settings: Any) -> Dispatcher:
    """Build a dispatcher; sessions are opened only for the duration of a handler."""
    dispatcher = Dispatcher(storage=MemoryStorage())
    router = Router(name="qr_bot")
    _install_handlers(router, session_factory, settings)
    dispatcher.include_router(router)
    return dispatcher


def create_bot(settings: Any) -> Bot:
    """Construct a Telegram bot from settings without creating a global singleton."""
    return Bot(
        token=_setting(settings, "bot_token"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


# Alias kept for integrations that use the more explicit name.
build_dispatcher = create_dispatcher


async def run_polling(settings: Any) -> None:
    """Run Telegram polling with a short-lived database session factory."""
    from app.db import build_session_factory

    bot = create_bot(settings)
    dispatcher = create_dispatcher(build_session_factory(_setting(settings, "database_url")), settings)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()

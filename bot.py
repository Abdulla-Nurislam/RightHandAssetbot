"""Telegram Lead-Capture Bot — aiogram 3 · Production Build
=========================================================
Три воронки строго по ТЗ:
  1. Коммерческая недвижимость — карточка → вид деятельности → дата → время → телефон
  2. ЖК Rams City              — карточка → способ оплаты → телефон
  3. Maserati                  — карточка → дата → время → расчёт → телефон

Фотографии загружаются из локальных папок на диске.
Все тексты хранятся в словаре TEXTS.
"""

from __future__ import annotations

import asyncio
import calendar
import glob
import logging
import os
import sys
from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Contact,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1.  КОНФИГУРАЦИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN: str = "8624784500:AAG5SKj9780_a_K2oiqkdjzQfNEfkAoV21U"
ADMIN_ID: int = 8184332888

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMMERCIAL_PHOTOS_DIR = os.path.join(BASE_DIR, "commercial real estate")
RAMS_PHOTOS_DIR       = os.path.join(BASE_DIR, "RAMS_PHOTOS")
MASERATI_PHOTOS_DIR   = os.path.join(BASE_DIR, "MASERATI_PHOTOS")
MAX_ALBUM_PHOTOS = 10

# ── Время для выбора ──
TIME_SLOTS = [
    ("🌅 10:00 – 12:00", "10:00–12:00"),
    ("☀️ 12:00 – 14:00", "12:00–14:00"),
    ("🌤 14:00 – 16:00", "14:00–16:00"),
    ("🌇 16:00 – 18:00", "16:00–18:00"),
    ("🌆 18:00 – 20:00", "18:00–20:00"),
]

# ── Названия месяцев ──
MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

TEXTS: dict[str, str] = {
    "start": (
        "🤖 Здравствуйте! Рады приветствовать вас.\n\n"
        "Этот бот создан для быстрой связи по ключевым активам. "
        "Пожалуйста, выберите интересующее вас направление на панели ниже, "
        "чтобы получить подробную информацию, презентацию и связаться напрямую:\n\n"
        "🏢 <b>Коммерческая недвижимость</b> — аренда площадей под бизнес.\n"
        "🏠 <b>ЖК Rams City</b> — стильная 2-комнатная квартира в престижном районе.\n"
        "🏎 <b>Maserati</b> — новый премиальный автомобиль в идеальном состоянии.\n\n"
        "Выберите раздел:"
    ),
    "commercial_card": (
        "🏢 <b>Коммерческая недвижимость</b>\n\n"
        "📍 <b>Адрес:</b> г. Алматы, ул. Полежаева, 28д\n"
        "📐 <b>Площадь:</b> 85 кв.м\n\n"
        "🏷 <b>Назначение:</b> Идеально под офис, Центр экспертиз и оценки, "
        "Центр печати и полиграфии, профессиональные услуги и логистика, "
        "офис логистической или таможенно-брокерской компании, "
        "представительство / Шоурум строительных материалов, "
        "Сервис и специализированный ритейл или учебная студия.\n\n"
        "✅ <b>Особенности:</b> Высокие потолки 3,2м, отдельный вход, "
        "витражные окна, выделенная мощность 15 кВт.\n\n"
        "💰 <b>Условия:</b> Аренда <b>399 000 ₸/мес</b>.\n\n"
        "Нажмите кнопку ниже, чтобы задать вопрос или забронировать время для просмотра объекта."
    ),
    "commercial_ask_activity": (
        "Уточните, пожалуйста, под какой вид деятельности вы рассматриваете помещение?"
    ),
    "commercial_ask_date": "📅 Выберите удобную дату для просмотра помещения:",
    "commercial_ask_time": "🕐 Выберите удобное время для просмотра:",
    "commercial_ask_phone": (
        "Чтобы мы могли зафиксировать за вами условия и связаться "
        "для организации показа, нажмите кнопку <b>«📱 Поделиться контактом»</b> ниже."
    ),
    "rams_card": (
        "🏠 <b>Современная 2-комнатная (евротрешка) квартира в ЖК Rams City</b>\n\n"
        "📍 <b>Локация:</b> Бостандыкский район, ул. Утепова / Розыбакиева, "
        "ЖК Рамс Сити. Развитая инфраструктура, концепция «город в городе», "
        "закрытый безопасный двор.\n\n"
        "📐 <b>Параметры:</b> 3 комнаты, общая площадь 56 кв.м, 17 этаж из 18. "
        "Панорамный вид на Кок-тобе.\n\n"
        "🛋 <b>Состояние:</b> Современный ремонт / хоумстейджинг / "
        "с новой мебелью / техникой. Заезжай и живи.\n\n"
        "💰 <b>Стоимость:</b> <b>54 990 000 тенге</b>.\n\n"
        "Чтобы узнать детали сделки или договориться о просмотре, нажмите кнопку ниже."
    ),
    "rams_ask_payment": "Каким способом вы планируете покупку квартиры?",
    "rams_ask_phone": (
        "Спасибо! Пожалуйста, нажмите кнопку <b>«📱 Поделиться контактом»</b>, "
        "чтобы наш менеджер связался с вами и подготовил необходимые документы "
        "для обсуждения сделки."
    ),
    "maserati_card": (
        "🏎 <b>Эксклюзивный автомобиль Maserati</b>\n\n"
        "🚗 <b>Модель:</b> Ghibli / Levante\n"
        "📅 <b>Год выпуска:</b> 2022 г.\n"
        "🛣 <b>Пробег:</b> 15 000 км\n"
        "⚙️ <b>Двигатель:</b> 3.0 л / 350 л.с.\n\n"
        "✅ <b>Состояние:</b> Идеальное техническое и эстетическое состояние. "
        "Обслуживался строго по регламенту. Салон — премиальная кожа, кузов в бронеплёнке.\n\n"
        "💰 <b>Цена:</b> <b>45 000 000 ₸</b>.\n\n"
        "Нажмите кнопку ниже, чтобы записаться на тест-драйв "
        "или получить подробный видеообзор автомобиля."
    ),
    "maserati_ask_date": "📅 Выберите удобную дату для тест-драйва / осмотра:",
    "maserati_ask_time": "🕐 Выберите удобное время:",
    "maserati_ask_payment": "Какой вариант расчёта или обмена вас интересует?",
    "maserati_ask_phone": (
        "Отлично. Нажмите кнопку <b>«📱 Поделиться контактом»</b> ниже. "
        "Мы свяжемся с вами в течение 15 минут, чтобы согласовать удобное "
        "время и место для осмотра автомобиля."
    ),
    "lead_submitted": (
        "✅ <b>Заявка успешно принята!</b>\n\n"
        "Благодарим вас за проявленный интерес. "
        "Информация уже передана владельцу.\n"
        "Мы свяжемся с вами в ближайшее время по указанному номеру телефона.\n\n"
        "Если вы хотите посмотреть другие объекты, нажмите кнопку ниже."
    ),
    "not_understood": (
        "⚠️ Действие не распознано. Пожалуйста, выберите один из предложенных вариантов."
    ),
    "cancelled": "❌ Действие отменено. Возвращаемся в главное меню…",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2.  ЛОГИРОВАНИЕ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3.  FSM СОСТОЯНИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CommercialFSM(StatesGroup):
    activity        = State()
    activity_custom = State()
    view_date       = State()
    view_time       = State()
    phone           = State()


class RamsFSM(StatesGroup):
    payment = State()
    phone   = State()


class MaseratiFSM(StatesGroup):
    meet_date = State()
    meet_time = State()
    payment   = State()
    phone     = State()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4.  КЛАВИАТУРЫ И КАЛЕНДАРЬ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_MENU_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏢 Коммерческая недвижимость")],
        [KeyboardButton(text="🏠 Квартира Rams City")],
        [KeyboardButton(text="🏎 Автомобиль Maserati")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


def _inline(*rows: tuple[str, str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=d)] for t, d in rows
        ]
    )


def _share_contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _back_to_menu_inline() -> InlineKeyboardMarkup:
    return _inline(("⬅️ Вернуться в главное меню", "go_main"))


def _time_slots_kb(prefix: str) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с временными слотами."""
    rows = [(label, f"{prefix}_time_{val}") for label, val in TIME_SLOTS]
    rows.append(("⬅️ Назад в меню", "go_main"))
    return _inline(*rows)


def build_calendar(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    """Строит интерактивный календарь."""
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([
        InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_prev_{year}_{month}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES[month]} {year}", callback_data=f"{prefix}_ign"),
        InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_next_{year}_{month}"),
    ])
    rows.append([
        InlineKeyboardButton(text=d, callback_data=f"{prefix}_ign")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    ])
    today = datetime.now()
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=f"{prefix}_ign"))
            elif datetime(year, month, day).date() < today.date():
                row.append(InlineKeyboardButton(text="·", callback_data=f"{prefix}_ign"))
            else:
                row.append(InlineKeyboardButton(
                    text=str(day),
                    callback_data=f"{prefix}_day_{year}_{month}_{day}",
                ))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="go_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5.  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _get_local_photos(folder: str) -> list[str]:
    exts = ("*.jpg", "*.jpeg", "*.png", "*.webp")
    files: list[str] = []
    for ext in exts:
        files += glob.glob(os.path.join(folder, ext))
    return sorted(files)[:MAX_ALBUM_PHOTOS]


async def _send_album(message: Message, folder: str) -> None:
    photos = _get_local_photos(folder)
    if not photos:
        logger.warning("No photos found in: %s", folder)
        return
    try:
        media = [types.InputMediaPhoto(media=FSInputFile(p)) for p in photos]
        await message.answer_media_group(media=media)
    except Exception:
        logger.exception("Failed to send album from %s", folder)


async def _show_main_menu(target: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(target, CallbackQuery):
        await target.message.answer(TEXTS["start"], reply_markup=MAIN_MENU_KB)
        await target.answer()
    else:
        await target.answer(TEXTS["start"], reply_markup=MAIN_MENU_KB)


async def _send_lead_to_admin(
    bot: Bot,
    direction: str,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    phone: str,
    answers: dict[str, Any],
) -> None:
    answers_text = "\n".join(f"  • {k}: {v}" for k, v in answers.items())
    full_name = f"{first_name or ''} {last_name or ''}".strip() or "не указано"
    text = (
        "🔔 <b>Новый лид из бота!</b>\n\n"
        f"📂 <b>Направление:</b> {direction}\n"
        f"👤 <b>Пользователь:</b> {full_name} (@{username or 'без юзернейма'})\n"
        f"📱 <b>Телефон:</b> {phone}\n\n"
        f"📝 <b>Ответы на вопросы:</b>\n{answers_text}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text)
        logger.info("Lead → admin %s | direction: %s", ADMIN_ID, direction)
    except Exception:
        logger.exception("CRITICAL — lead NOT delivered to admin %s", ADMIN_ID)


async def _finalize_lead(message: Message, state: FSMContext, direction: str) -> None:
    contact: Contact = message.contact
    phone = contact.phone_number
    data = await state.get_data()
    answers = {k: v for k, v in data.items() if k != "direction"}

    await _send_lead_to_admin(
        bot=message.bot,
        direction=direction,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        phone=phone,
        answers=answers,
    )
    await state.clear()
    await message.answer("✅ Контакт получен!", reply_markup=ReplyKeyboardRemove())
    await message.answer(TEXTS["lead_submitted"], reply_markup=_back_to_menu_inline())


async def _handle_calendar(
    callback: CallbackQuery, state: FSMContext, prefix: str,
    next_state: State, next_text_key: str, next_kb_builder,
) -> None:
    """Обработчик событий календаря (навигация и выбор дня)."""
    parts = callback.data.split("_")
    action = parts[1]
    if action == "ign":
        await callback.answer()
        return
    year, month = int(parts[2]), int(parts[3])
    if action == "prev":
        month -= 1
        if month < 1:
            month, year = 12, year - 1
        await callback.message.edit_reply_markup(reply_markup=build_calendar(year, month, prefix))
    elif action == "next":
        month += 1
        if month > 12:
            month, year = 1, year + 1
        await callback.message.edit_reply_markup(reply_markup=build_calendar(year, month, prefix))
    elif action == "day":
        day = int(parts[4])
        selected = f"{day:02d}.{month:02d}.{year}"
        await state.update_data(**{"Дата встречи": selected})
        await state.set_state(next_state)
        await callback.message.edit_text(f"📅 Выбрана дата: <b>{selected}</b>")
        await callback.message.answer(TEXTS[next_text_key], reply_markup=next_kb_builder())
    await callback.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6.  РОУТЕР И ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = Router(name="main")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _show_main_menu(message, state)
    logger.info("User %s started the bot.", message.from_user.id)


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(TEXTS["cancelled"], reply_markup=MAIN_MENU_KB)


@router.callback_query(F.data == "go_main")
async def cb_go_main(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_main_menu(callback, state)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7.  ВЕТКА 1 — КОММЕРЧЕСКАЯ НЕДВИЖИМОСТЬ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.message(F.text == "🏢 Коммерческая недвижимость")
async def show_commercial(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_album(message, COMMERCIAL_PHOTOS_DIR)
    kb = _inline(
        ("📩 Оставить заявку / Задать вопрос", "com_apply"),
        ("⬅️ Назад в меню", "go_main"),
    )
    await message.answer(TEXTS["commercial_card"], reply_markup=kb)


@router.callback_query(F.data == "com_apply")
async def com_ask_activity(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CommercialFSM.activity)
    await state.update_data(direction="Коммерция")
    kb = _inline(
        ("🏢 Офис", "com_act_office"),
        ("🛒 Магазин / Ритейл", "com_act_retail"),
        ("🖨 Копи-центр / Пошивочный цех", "com_act_copy"),
        ("✏️ Другое (ввод текстом)", "com_act_other"),
        ("⬅️ Назад в меню", "go_main"),
    )
    await callback.message.answer(TEXTS["commercial_ask_activity"], reply_markup=kb)
    await callback.answer()


@router.callback_query(CommercialFSM.activity, F.data.startswith("com_act_"))
async def com_activity_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    mapping = {
        "com_act_office": "Офис",
        "com_act_retail": "Магазин / Ритейл",
        "com_act_copy":   "Копи-центр / Пошивочный цех",
    }
    if callback.data == "com_act_other":
        await state.set_state(CommercialFSM.activity_custom)
        await callback.message.answer("✏️ Введите вид деятельности текстом:")
        await callback.answer()
        return

    await state.update_data(**{"Вид деятельности": mapping[callback.data]})
    await state.set_state(CommercialFSM.view_date)
    now = datetime.now()
    await callback.message.answer(
        TEXTS["commercial_ask_date"],
        reply_markup=build_calendar(now.year, now.month, "comcal"),
    )
    await callback.answer()


@router.message(CommercialFSM.activity_custom, F.text)
async def com_activity_custom_text(message: Message, state: FSMContext) -> None:
    await state.update_data(**{"Вид деятельности": message.text})
    await state.set_state(CommercialFSM.view_date)
    now = datetime.now()
    await message.answer(
        TEXTS["commercial_ask_date"],
        reply_markup=build_calendar(now.year, now.month, "comcal"),
    )


@router.callback_query(CommercialFSM.view_date, F.data.startswith("comcal_"))
async def com_calendar(callback: CallbackQuery, state: FSMContext) -> None:
    await _handle_calendar(callback, state, "comcal",
                           CommercialFSM.view_time, "commercial_ask_time",
                           lambda: _time_slots_kb("com"))


@router.message(CommercialFSM.view_date)
async def com_date_fallback(message: Message) -> None:
    await message.answer("⚠️ Выберите дату из календаря выше.")


@router.callback_query(CommercialFSM.view_time, F.data.startswith("com_time_"))
async def com_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    time_val = callback.data.replace("com_time_", "")
    await state.update_data(**{"Время встречи": time_val})
    await state.set_state(CommercialFSM.phone)
    await callback.message.edit_text(f"🕐 Время: <b>{time_val}</b>")
    await callback.message.answer(
        TEXTS["commercial_ask_phone"], reply_markup=_share_contact_kb()
    )
    await callback.answer()


@router.message(CommercialFSM.view_time)
async def com_time_fallback(message: Message) -> None:
    await message.answer("⚠️ Выберите время из вариантов выше.")


@router.message(CommercialFSM.phone, F.contact)
async def com_phone_received(message: Message, state: FSMContext) -> None:
    await _finalize_lead(message, state, direction="Коммерция")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8.  ВЕТКА 2 — КВАРТИРА ЖК RAMS CITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.message(F.text == "🏠 Квартира Rams City")
async def show_rams(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_album(message, RAMS_PHOTOS_DIR)
    kb = _inline(
        ("🔑 Узнать условия покупки", "rams_conditions"),
        ("⬅️ Назад в меню", "go_main"),
    )
    await message.answer(TEXTS["rams_card"], reply_markup=kb)


@router.callback_query(F.data == "rams_conditions")
async def rams_ask_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RamsFSM.payment)
    await state.update_data(direction="Rams City")
    kb = _inline(
        ("💵 100% оплата", "rams_pay_full"),
        ("🏦 Ипотека", "rams_pay_mortgage"),
        ("⏳ Рассрочка", "rams_pay_installment"),
        ("⬅️ Назад в меню", "go_main"),
    )
    await callback.message.answer(TEXTS["rams_ask_payment"], reply_markup=kb)
    await callback.answer()


@router.callback_query(RamsFSM.payment, F.data.startswith("rams_pay_"))
async def rams_payment_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    mapping = {
        "rams_pay_full":        "100% оплата",
        "rams_pay_mortgage":    "Ипотека",
        "rams_pay_installment": "Рассрочка",
    }
    await state.update_data(**{"Способ покупки": mapping[callback.data]})
    await state.set_state(RamsFSM.phone)
    await callback.message.answer(
        TEXTS["rams_ask_phone"], reply_markup=_share_contact_kb()
    )
    await callback.answer()


@router.message(RamsFSM.phone, F.contact)
async def rams_phone_received(message: Message, state: FSMContext) -> None:
    await _finalize_lead(message, state, direction="Rams City")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9.  ВЕТКА 3 — АВТОМОБИЛЬ MASERATI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.message(F.text == "🏎 Автомобиль Maserati")
async def show_maserati(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_album(message, MASERATI_PHOTOS_DIR)
    kb = _inline(
        ("🏁 Записаться на тест-драйв / Осмотр", "mas_testdrive"),
        ("⬅️ Назад в меню", "go_main"),
    )
    await message.answer(TEXTS["maserati_card"], reply_markup=kb)


@router.callback_query(F.data == "mas_testdrive")
async def mas_ask_date(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MaseratiFSM.meet_date)
    await state.update_data(direction="Maserati")
    now = datetime.now()
    await callback.message.answer(
        TEXTS["maserati_ask_date"],
        reply_markup=build_calendar(now.year, now.month, "mascal"),
    )
    await callback.answer()


@router.callback_query(MaseratiFSM.meet_date, F.data.startswith("mascal_"))
async def mas_calendar(callback: CallbackQuery, state: FSMContext) -> None:
    await _handle_calendar(callback, state, "mascal",
                           MaseratiFSM.meet_time, "maserati_ask_time",
                           lambda: _time_slots_kb("mas"))


@router.message(MaseratiFSM.meet_date)
async def mas_date_fallback(message: Message) -> None:
    await message.answer("⚠️ Выберите дату из календаря выше.")


@router.callback_query(MaseratiFSM.meet_time, F.data.startswith("mas_time_"))
async def mas_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    time_val = callback.data.replace("mas_time_", "")
    await state.update_data(**{"Время встречи": time_val})
    await state.set_state(MaseratiFSM.payment)
    await callback.message.edit_text(f"🕐 Время: <b>{time_val}</b>")
    kb = _inline(
        ("💵 Наличный расчёт", "mas_pay_cash"),
        ("🏦 Автокредит", "mas_pay_credit"),
        ("🔄 Обмен (Trade-In)", "mas_pay_trade"),
        ("⬅️ Назад в меню", "go_main"),
    )
    await callback.message.answer(TEXTS["maserati_ask_payment"], reply_markup=kb)
    await callback.answer()


@router.message(MaseratiFSM.meet_time)
async def mas_time_fallback(message: Message) -> None:
    await message.answer("⚠️ Выберите время из вариантов выше.")


@router.callback_query(MaseratiFSM.payment, F.data.startswith("mas_pay_"))
async def mas_payment_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    mapping = {
        "mas_pay_cash":   "Наличный расчёт",
        "mas_pay_credit": "Автокредит",
        "mas_pay_trade":  "Обмен (Trade-In)",
    }
    await state.update_data(**{"Вариант расчёта": mapping[callback.data]})
    await state.set_state(MaseratiFSM.phone)
    await callback.message.answer(
        TEXTS["maserati_ask_phone"], reply_markup=_share_contact_kb()
    )
    await callback.answer()


@router.message(MaseratiFSM.phone, F.contact)
async def mas_phone_received(message: Message, state: FSMContext) -> None:
    await _finalize_lead(message, state, direction="Maserati")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. FALLBACK ОБРАБОТЧИКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.message(
    StateFilter(CommercialFSM.phone, RamsFSM.phone, MaseratiFSM.phone),
    ~F.contact,
)
async def phone_state_fallback(message: Message) -> None:
    await message.answer(
        "⚠️ Пожалуйста, нажмите кнопку <b>«📱 Поделиться контактом»</b> ниже.",
        reply_markup=_share_contact_kb(),
    )


@router.message(CommercialFSM.activity)
async def com_activity_fallback(message: Message) -> None:
    await message.answer(TEXTS["not_understood"])


@router.message(F.sticker)
async def sticker_fallback(message: Message) -> None:
    await message.answer(TEXTS["not_understood"])


@router.callback_query()
async def unmatched_callback(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS["not_understood"], show_alert=True)


@router.message()
async def general_fallback(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await message.answer(
        TEXTS["not_understood"],
        reply_markup=None if current else MAIN_MENU_KB,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. ТОЧКА ВХОДА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Bot is starting polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
"""Almaty RE-Tech Club Bot — aiogram 3 · Production Build
=========================================================
Архитектура:
  /start → Верификация контакта (Google Sheets «Резиденты»)
    ├── Найден  → Клубное меню: О клубе / События / Привилегии / Кабинет
    │               Привилегии → Коммерция / Rams City / Maserati (воронки)
    └── Не найден → Подать заявку (FSM скрининг + стоп-слова)
                   → Связаться со службой заботы
"""

from __future__ import annotations

import asyncio
import calendar
import glob
import logging
import os
import re
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

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1.  КОНФИГУРАЦИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN: str = "8983299294:AAFpZJVnrAva2f8hJvgJYY-pu1877d3jwrw"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMMERCIAL_PHOTOS_DIR = os.path.join(BASE_DIR, "commercial real estate")
RAMS_PHOTOS_DIR       = os.path.join(BASE_DIR, "RAMS_PHOTOS")
MASERATI_PHOTOS_DIR   = os.path.join(BASE_DIR, "MASERATI_PHOTOS")

# Максимум фото в альбоме — Telegram принимает до 10 файлов за раз,
# но при большом размере лучше ограничиться 5 чтобы избежать таймаута.
MAX_ALBUM_PHOTOS = 5

CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
SPREADSHEET_ID: str = "1szL5sNAQMN0c90kb9j8Z8Qiw3mZ6Kpmj3EaYsErO8Lw"
SHEET_RESIDENTS = "Резиденты"
SHEET_WAITLIST  = "waitlist"
SHEET_APPROVED  = "Approved"
SHEET_LEADS     = "Лиды & События"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Стоп-слова для автоматического скрининга
STOP_WORDS = {
    "студент", "student", "безработн", "без работы", "не работаю",
    "школьник", "пенсионер", "мошенник", "спам", "spam",
    "без денег", "нет денег", "ищу спонсора", "ищу инвестора",
    "нет организации", "no organization",
}

# Временные слоты для выбора
TIME_SLOTS = [
    ("🌅 10:00 – 12:00", "t1000_1200"),
    ("☀️ 12:00 – 14:00", "t1200_1400"),
    ("🌤 14:00 – 16:00", "t1400_1600"),
    ("🌇 16:00 – 18:00", "t1600_1800"),
    ("🌆 18:00 – 20:00", "t1800_2000"),
]

# Читаемое значение времени для записи в таблицу
TIME_LABELS = {
    "t1000_1200": "10:00–12:00",
    "t1200_1400": "12:00–14:00",
    "t1400_1600": "14:00–16:00",
    "t1600_1800": "16:00–18:00",
    "t1800_2000": "18:00–20:00",
}

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2.  ТЕКСТЫ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEXTS: dict[str, str] = {
    # ── Авторизация ──
    "welcome": (
        "🔐 <b>Добро пожаловать в Almaty RE-Tech Club.</b>\n\n"
        "Для верификации вашего членства, пожалуйста, нажмите кнопку ниже.\n\n"
        "<i>Ваш номер будет сверен с реестром резидентов клуба.</i>"
    ),
    "contact_required": (
        "⚠️ Для верификации необходимо нажать кнопку "
        "<b>«🔐 Подтвердить членство в клубе»</b> ниже.\n\n"
        "Ручной ввод номера не принимается в целях безопасности."
    ),
    "auth_success": (
        "✅ <b>Авторизация успешна.</b>\n\n"
        "Рады видеть вас в клубе, <b>{name}</b>!\n"
        "Ваш текущий статус: <b>{status}</b>.\n\n"
        "Выберите раздел из меню ниже:"
    ),
    "auth_fail": (
        "🚫 К сожалению, указанный номер <b>отсутствует</b> в списке "
        "действующих резидентов клуба.\n\n"
        "Вы можете подать заявку на вступление или связаться "
        "со службой заботы о клиентах."
    ),

    # ── Меню клуба ──
    "about_club": (
        "🏛 <b>О клубе Business Solutions</b>\n\n"
        "Business Solutions Club — это премиальное закрытое сообщество, "
        "объединяющее ведущих девелоперов, инвесторов, PropTech-предпринимателей "
        "и лидеров рынка недвижимости и технологий.\n\n"
        "📋 <b>Правила клуба:</b>\n"
        "• 🔒 <b>Конфиденциальность</b> — информация о членах и событиях клуба "
        "не подлежит разглашению.\n"
        "• 🤝 <b>Взаимоуважение</b> — все участники взаимодействуют в духе "
        "партнёрства и профессионализма.\n"
        "• 🎯 <b>Качество сделок</b> — мы работаем только с верифицированными "
        "активами и проверенными контрагентами.\n\n"
        "Для вопросов и предложений: @BS_club_support"
    ),
    "events": (
        "📅 <b>Предстоящие события клуба</b>\n\n"
        "Выберите мероприятие, чтобы зарегистрироваться:"
    ),
    "cabinet": (
        "🪪 <b>Ваш цифровой кабинет резидента</b>\n\n"
        "👤 <b>Имя:</b> {name}\n"
        "🏅 <b>Статус:</b> {status}\n"
        "📱 <b>Телефон:</b> {phone}\n"
        "📅 <b>Дата вступления:</b> {joined}\n\n"
        "<i>Данные актуальны на момент последней авторизации.</i>"
    ),
    "privileges": (
        "💎 <b>Эксклюзивные привилегии клуба</b>\n\n"
        "Резидентам Business Solutions Club доступны уникальные предложения "
        "по ключевым активам. Выберите направление:"
    ),

    # ── События ──
    "event_proptech": (
        "🎤 <b>PropTech Forum 2025</b>\n\n"
        "📅 Дата: 25 июля 2025, 18:00\n"
        "📍 Место: Almaty Marriott Hotel, зал «Алатау»\n\n"
        "Ключевые спикеры: CTO Баiтерек Девелопмент, "
        "основатель Homepro.kz, Head of RE Kaspi.\n\n"
        "Количество мест ограничено — 40 резидентов."
    ),
    "event_dinner": (
        "🍷 <b>Закрытый ужин резидентов</b>\n\n"
        "📅 Дата: 12 августа 2025, 20:00\n"
        "📍 Место: Ресторан «Пиросмани», приватный зал\n\n"
        "Неформальный нетворкинг в кругу 20 ключевых игроков "
        "рынка недвижимости Алматы."
    ),
    "event_booked": (
        "✅ <b>Вы зарегистрированы!</b>\n\n"
        "Ваше место на <b>{event}</b> забронировано.\n"
        "Детали и адрес будут отправлены за 24 часа до события.\n\n"
        "По вопросам: @BS_club_support"
    ),

    # ── Служба заботы ──
    "support": (
        "📞 <b>Служба заботы о клиентах</b>\n\n"
        "Для связи с менеджером клуба, пожалуйста, "
        "напишите нам: @BS_club_support\n\n"
        "Или позвоните: +7 (700) 000-00-00\n\n"
        "Мы доступны с 10:00 до 20:00 (Алматы, UTC+5)."
    ),

    # ── Скрининг ──
    "screening_start": (
        "📋 <b>Заявка на вступление в клуб</b>\n\n"
        "Для рассмотрения вашей кандидатуры, пожалуйста, "
        "ответьте на несколько вопросов.\n\n"
        "Введите ваше <b>ФИО</b> (Фамилия Имя Отчество):"
    ),
    "screening_company": "Укажите вашу <b>компанию и сферу деятельности:</b>",
    "screening_interest": (
        "Какова <b>цель вступления</b> в клуб?\n"
        "(инвестиции, нетворкинг, партнёрство, другое)"
    ),
    "screening_referral": (
        "Кто <b>рекомендовал</b> вам наш клуб?\n"
        "(имя рекомендателя или «самостоятельно нашёл»)"
    ),
    "screening_passed": (
        "✅ <b>Заявка принята!</b>\n\n"
        "Ваша анкета передана на рассмотрение службе безопасности клуба. "
        "Мы уведомим вас о решении в течение 48 часов.\n\n"
        "Благодарим за интерес к Business Solutions Club."
    ),
    "screening_flagged": (
        "📋 <b>Заявка принята на рассмотрение.</b>\n\n"
        "Ваша анкета будет изучена нашей командой. "
        "Мы свяжемся с вами в течение 5 рабочих дней.\n\n"
        "По срочным вопросам: @BS_club_support"
    ),

    # ── Воронки (лиды) ──
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
    "rams_ask_readiness": "Насколько вы готовы к сделке?",
    "rams_ask_phone": (
        "Спасибо! Пожалуйста, нажмите кнопку <b>«📱 Поделиться контактом»</b>, "
        "чтобы наш менеджер связался с вами и подготовил необходимые документы "
        "для обсуждения сделки."
    ),
    # Карточка Maserati
    "maserati_card": (
        "🏎 <b>Maserati GranTurismo Trofeo</b>\n\n"
        "Эксклюзивный итальянский гранд-турер в максимальной комплектации, "
        "объединяющий гоночную динамику и эталонный комфорт.\n\n"
        "⚙️ <b>Двигатель:</b> 3.0 V6 Nettuno Twin-Turbo\n"
        "🐎 <b>Мощность:</b> 550 л.с. / 650 Нм\n"
        "⏱ <b>Разгон 0-100 км/ч:</b> 3.5 сек\n"
        "🏁 <b>Макс. скорость:</b> 320 км/ч\n"
        "🏎 <b>Привод:</b> Полный (AWD)\n\n"
        "Пробег: 0 км (оригинал, подтвержден историей обслуживания)\n"
        "💎 <b>Особенности:</b> Карбоновый декор экстерьера, премиальная аудиосистема Sonus faber, "
        "спортивные сиденья с отделкой перфорированной кожей, кованые диски.\n\n"
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
        "⚠️ Действие не распознано. Пожалуйста, выберите один "
        "из предложенных вариантов."
    ),
    "cancelled": "❌ Действие отменено. Возвращаемся в главное меню…",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3.  ЛОГИРОВАНИЕ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4.  GOOGLE SHEETS — АСИНХРОННАЯ ОБЁРТКА
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_gspread_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    elif digits.startswith("7") and len(digits) == 11:
        pass
    return digits


async def sheets_lookup_phone(phone: str) -> dict | None:
    """Ищет резидента по номеру телефона. Возвращает dict или None."""
    normalized = _normalize_phone(phone)

    def _lookup():
        client = _get_gspread_client()
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_RESIDENTS)
        records = ws.get_all_records()
        for row in records:
            raw = str(row.get("Телефон", ""))
            if _normalize_phone(raw) == normalized:
                return row
        return None

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        logger.exception("sheets_lookup_phone error for %s", phone)
        return None


async def sheets_append_waitlist(row: list) -> None:
    def _append():
        client = _get_gspread_client()
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_WAITLIST)
        ws.append_row(row)

    try:
        await asyncio.to_thread(_append)
    except Exception:
        logger.exception("sheets_append_waitlist error")


async def sheets_append_approved(row: list) -> None:
    def _append():
        client = _get_gspread_client()
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_APPROVED)
        ws.append_row(row)

    try:
        await asyncio.to_thread(_append)
    except Exception:
        logger.exception("sheets_append_approved error")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5.  FSM СОСТОЯНИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AuthFSM(StatesGroup):
    waiting_contact = State()


class ScreeningFSM(StatesGroup):
    full_name = State()
    company   = State()
    interest  = State()
    referral  = State()


class CommercialFSM(StatesGroup):
    activity        = State()
    activity_custom = State()
    view_date       = State()
    view_time       = State()
    phone           = State()


class RamsFSM(StatesGroup):
    payment   = State()
    readiness = State()
    phone     = State()


class MaseratiFSM(StatesGroup):
    meet_date = State()
    meet_time = State()
    payment   = State()
    phone     = State()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6.  КЛАВИАТУРЫ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AUTH_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔐 Подтвердить членство в клубе", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

CLUB_MENU_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏛 О клубе"), KeyboardButton(text="📅 События")],
        [KeyboardButton(text="💎 Привилегии"), KeyboardButton(text="🪪 Кабинет")],
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


def _time_slots_kb(prefix: str) -> InlineKeyboardMarkup:
    rows = [(label, f"{prefix}_time_{val}") for label, val in TIME_SLOTS]
    rows.append(("⬅️ Назад в меню", "go_club_menu"))
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
    rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="go_club_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7.  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _get_local_photos(folder: str, max_count: int = MAX_ALBUM_PHOTOS) -> list[str]:
    """Возвращает список jpg/jpeg/png файлов, отсортированных по размеру (наименьшие первыми)."""
    # Только форматы, которые принимает Telegram через upload
    exts = ("*.jpg", "*.jpeg", "*.png")
    files: list[str] = []
    for ext in exts:
        files += glob.glob(os.path.join(folder, ext))
    # Сортируем по размеру файла — небольшие грузятся быстрее
    files.sort(key=lambda p: os.path.getsize(p))
    return files[:max_count]


async def _send_photos(message: Message, folder: str) -> None:
    """
    Отправляет фотографии как медиа-группу (один альбом в Telegram).
    Если фото больше 10, они отправляются несколькими альбомами.
    """
    photos = _get_local_photos(folder, max_count=9999)
    if not photos:
        logger.warning("No photos found in: %s", folder)
        return
    
    chunk_size = 10
    for i in range(0, len(photos), chunk_size):
        chunk = photos[i:i + chunk_size]
        try:
            media = [types.InputMediaPhoto(media=FSInputFile(p)) for p in chunk]
            await message.answer_media_group(media=media)
            if len(photos) > chunk_size:
                await asyncio.sleep(1.0)
        except Exception:
            logger.exception("Failed to send album chunk from %s", folder)


async def sheets_append_lead(row: list) -> None:
    """Записывает лид в лист «Лиды» Google Sheets."""
    def _append():
        client = _get_gspread_client()
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_LEADS)
        ws.append_row(row)

    try:
        await asyncio.to_thread(_append)
        logger.info("Lead saved to Sheets: %s", row)
    except Exception:
        logger.exception("sheets_append_lead error")


async def _finalize_lead(message: Message, state: FSMContext, direction: str) -> None:
    contact: Contact = message.contact
    phone = contact.phone_number
    data = await state.get_data()
    answers = {k: v for k, v in data.items() if k not in ("direction", "resident", "unauthorized_phone")}

    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or "—"
    answers_str = " | ".join(f"{k}: {v}" for k, v in answers.items())

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        direction,
        full_name,
        f"@{message.from_user.username}" if message.from_user.username else "—",
        phone,
        answers_str,
    ]
    await sheets_append_lead(row)

    await state.clear()
    await message.answer("✅ Контакт получен!", reply_markup=ReplyKeyboardRemove())
    kb = _inline(
        ("💎 Посмотреть другие привилегии", "go_privileges"),
        ("⬅️ Главное меню", "go_club_menu"),
    )
    await message.answer(TEXTS["lead_submitted"], reply_markup=kb)


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
# 8.  РОУТЕР И СТАРТ / АВТОРИЗАЦИЯ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = Router(name="main")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AuthFSM.waiting_contact)
    await message.answer(TEXTS["welcome"], reply_markup=AUTH_KB)
    logger.info("User %s started the bot.", message.from_user.id)


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current and current.startswith("AuthFSM"):
        await message.answer(TEXTS["cancelled"], reply_markup=ReplyKeyboardRemove())
        await message.answer(TEXTS["welcome"], reply_markup=AUTH_KB)
        await state.set_state(AuthFSM.waiting_contact)
    else:
        await message.answer(TEXTS["cancelled"], reply_markup=CLUB_MENU_KB)


@router.message(AuthFSM.waiting_contact, F.contact)
async def auth_contact_received(message: Message, state: FSMContext) -> None:
    """Получаем контакт, ищем в Google Sheets."""
    phone = message.contact.phone_number
    await message.answer("🔍 Проверяю данные…", reply_markup=ReplyKeyboardRemove())

    resident = await sheets_lookup_phone(phone)

    if resident:
        await state.clear()
        await state.update_data(resident=resident)
        await message.answer(
            TEXTS["auth_success"].format(
                name=resident.get("Имя", resident.get("name", "Резидент")),
                status=resident.get("Статус", resident.get("status", "Резидент")),
            ),
            reply_markup=CLUB_MENU_KB,
        )
        logger.info("Auth SUCCESS: user=%s", message.from_user.id)
    else:
        await state.clear()
        await state.update_data(unauthorized_phone=phone)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📋 Подать заявку на вступление",
                callback_data="apply_membership",
            )],
            [InlineKeyboardButton(
                text="📞 Связаться со службой заботы",
                callback_data="contact_support",
            )],
        ])
        await message.answer(TEXTS["auth_fail"], reply_markup=kb)
        logger.info("Auth FAIL: user=%s phone=%s", message.from_user.id, phone)


@router.message(AuthFSM.waiting_contact, ~F.contact)
async def auth_text_instead_of_contact(message: Message) -> None:
    """Пользователь ввёл текст вместо нажатия кнопки."""
    await message.answer(TEXTS["contact_required"], reply_markup=AUTH_KB)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9.  КЛУБНОЕ МЕНЮ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "go_club_menu")
async def go_club_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=CLUB_MENU_KB)
    await callback.answer()


@router.message(F.text == "🏛 О клубе")
async def about_club(message: Message) -> None:
    kb = _inline(("📞 Связаться с нами", "contact_support"))
    await message.answer(TEXTS["about_club"], reply_markup=kb)


@router.message(F.text == "📅 События")
async def show_events(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 PropTech Forum 25.07", callback_data="event_proptech")],
        [InlineKeyboardButton(text="🍷 Закрытый ужин 12.08", callback_data="event_dinner")],
    ])
    await message.answer(TEXTS["events"], reply_markup=kb)


@router.callback_query(F.data == "event_proptech")
async def event_proptech(callback: CallbackQuery) -> None:
    kb = _inline(
        ("✅ Забронировать место", "book_proptech"),
        ("⬅️ Назад", "go_club_menu"),
    )
    await callback.message.answer(TEXTS["event_proptech"], reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "event_dinner")
async def event_dinner(callback: CallbackQuery) -> None:
    kb = _inline(
        ("✅ Забронировать место", "book_dinner"),
        ("⬅️ Назад", "go_club_menu"),
    )
    await callback.message.answer(TEXTS["event_dinner"], reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.in_({"book_proptech", "book_dinner"}))
async def book_event(callback: CallbackQuery) -> None:
    event_name = "PropTech Forum 25.07" if callback.data == "book_proptech" else "Закрытый ужин 12.08"

    # Записываем бронь в лист «Лиды» как отдельное направление
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"Событие: {event_name}",
        f"{callback.from_user.first_name or ''} {callback.from_user.last_name or ''}".strip() or "—",
        f"@{callback.from_user.username}" if callback.from_user.username else "—",
        "—",  # телефон неизвестен на этом шаге
        "Запрос на бронирование места",
    ]
    await sheets_append_lead(row)

    await callback.message.answer(TEXTS["event_booked"].format(event=event_name))
    await callback.answer()


@router.message(F.text == "💎 Привилегии")
async def show_privileges(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Коммерческая недвижимость", callback_data="priv_commercial")],
        [InlineKeyboardButton(text="🏠 Квартира Rams City", callback_data="priv_rams")],
        [InlineKeyboardButton(text="🏎 Автомобиль Maserati", callback_data="priv_maserati")],
    ])
    await message.answer(TEXTS["privileges"], reply_markup=kb)


@router.callback_query(F.data == "go_privileges")
async def go_privileges(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Коммерческая недвижимость", callback_data="priv_commercial")],
        [InlineKeyboardButton(text="🏠 Квартира Rams City", callback_data="priv_rams")],
        [InlineKeyboardButton(text="🏎 Автомобиль Maserati", callback_data="priv_maserati")],
    ])
    await callback.message.answer(TEXTS["privileges"], reply_markup=kb)
    await callback.answer()


@router.message(F.text == "🪪 Кабинет")
async def show_cabinet(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    resident = data.get("resident", {})
    if not resident:
        await message.answer(
            "⚠️ Данные кабинета недоступны. Попробуйте пройти авторизацию заново: /start"
        )
        return
    await message.answer(
        TEXTS["cabinet"].format(
            name=resident.get("Имя", resident.get("name", "—")),
            status=resident.get("Статус", resident.get("status", "—")),
            phone=resident.get("Телефон", "—"),
            joined=resident.get("Дата вступления", resident.get("joined", "—")),
        )
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. СКРИНИНГ ЗАЯВКИ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "apply_membership")
async def start_screening(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает FSM скрининга заявки."""
    data = await state.get_data()
    phone = data.get("unauthorized_phone", "—")
    await state.clear()
    await state.update_data(unauthorized_phone=phone)
    await state.set_state(ScreeningFSM.full_name)
    await callback.message.answer(TEXTS["screening_start"])
    await callback.answer()


@router.message(ScreeningFSM.full_name, F.text)
async def screening_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text)
    await state.set_state(ScreeningFSM.company)
    await message.answer(TEXTS["screening_company"])


@router.message(ScreeningFSM.company, F.text)
async def screening_company(message: Message, state: FSMContext) -> None:
    await state.update_data(company=message.text)
    await state.set_state(ScreeningFSM.interest)
    await message.answer(TEXTS["screening_interest"])


@router.message(ScreeningFSM.interest, F.text)
async def screening_interest(message: Message, state: FSMContext) -> None:
    await state.update_data(interest=message.text)
    await state.set_state(ScreeningFSM.referral)
    await message.answer(TEXTS["screening_referral"])


@router.message(ScreeningFSM.referral, F.text)
async def screening_referral(message: Message, state: FSMContext) -> None:
    """Финальный шаг скрининга — проверка стоп-слов и запись в таблицу."""
    await state.update_data(referral=message.text)
    data = await state.get_data()

    # Объединяем все ответы в одну строку для проверки
    combined = " ".join([
        data.get("full_name", ""),
        data.get("company", ""),
        data.get("interest", ""),
        data.get("referral", ""),
    ]).lower()

    has_stop_word = any(word in combined for word in STOP_WORDS)

    phone = data.get("unauthorized_phone", "—")
    admin_msg = (
        f"📋 <b>Новая заявка на вступление в клуб</b>\n\n"
        f"👤 <b>ФИО:</b> {data.get('full_name')}\n"
        f"🏢 <b>Компания:</b> {data.get('company')}\n"
        f"🎯 <b>Цель:</b> {data.get('interest')}\n"
        f"🤝 <b>Рекомендатель:</b> {data.get('referral')}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"📱 <b>Username:</b> @{message.from_user.username or 'без юзернейма'}\n\n"
        f"🔍 <b>Скрининг:</b> {'🚫 СТОП-СЛОВО' if has_stop_word else '✅ Чистый'}\n"
        f"📄 <b>Лист:</b> {'waitlist' if has_stop_word else 'Approved'}"
    )

    row_data = [
        str(message.from_user.id),
        message.from_user.username or "",
        data.get("full_name", ""),
        data.get("company", ""),
        data.get("interest", ""),
        data.get("referral", ""),
        phone,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]

    post_screening_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Служба заботы", callback_data="contact_support")],
        [InlineKeyboardButton(text="🔄 Вернуться в начало", callback_data="start_over")],
    ])

    if has_stop_word:
        await sheets_append_waitlist(row_data + ["Отклонено системой скрининга (стоп-слова)"])
        await state.clear()
        await message.answer(TEXTS["screening_flagged"], reply_markup=post_screening_kb)
        logger.info("Screening FLAGGED: user=%s", message.from_user.id)
    else:
        await sheets_append_approved(row_data + ["✅ Автоскрининг пройден"])
        await state.clear()
        await message.answer(TEXTS["screening_passed"], reply_markup=post_screening_kb)
        logger.info("Screening PASSED: user=%s name=%s", message.from_user.id, data.get("full_name"))

    # Уведомление владельцу убрано — все данные уже записаны в листы Approved / waitlist


@router.callback_query(F.data == "start_over")
async def start_over_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AuthFSM.waiting_contact)
    await callback.message.answer(TEXTS["welcome"], reply_markup=AUTH_KB)
    await callback.answer()


@router.callback_query(F.data == "contact_support")
async def contact_support_callback(callback: CallbackQuery) -> None:
    await callback.message.answer(TEXTS["support"])
    await callback.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. ВЕТКА 1 — КОММЕРЧЕСКАЯ НЕДВИЖИМОСТЬ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "priv_commercial")
async def show_commercial(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _send_photos(callback.message, COMMERCIAL_PHOTOS_DIR)
    kb = _inline(
        ("📩 Оставить заявку / Задать вопрос", "com_apply"),
        ("⬅️ Назад в меню", "go_club_menu"),
    )
    await callback.message.answer(TEXTS["commercial_card"], reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "com_apply")
async def com_ask_activity(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CommercialFSM.activity)
    await state.update_data(direction="Коммерция")
    kb = _inline(
        ("🏢 Офис", "com_act_office"),
        ("🛒 Магазин / Ритейл", "com_act_retail"),
        ("🖨 Копи-центр / Пошивочный цех", "com_act_copy"),
        ("✏️ Другое (ввод текстом)", "com_act_other"),
        ("⬅️ Назад в меню", "go_club_menu"),
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
    await _handle_calendar(
        callback, state, "comcal",
        CommercialFSM.view_time, "commercial_ask_time",
        lambda: _time_slots_kb("com"),
    )


@router.message(CommercialFSM.view_date)
async def com_date_fallback(message: Message) -> None:
    await message.answer("⚠️ Выберите дату из календаря выше.")


@router.callback_query(CommercialFSM.view_time, F.data.startswith("com_time_"))
async def com_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.replace("com_time_", "")
    time_val = TIME_LABELS.get(key, key)  # читаемое время для записи
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
# 12. ВЕТКА 2 — КВАРТИРА ЖК RAMS CITY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "priv_rams")
async def show_rams(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _send_photos(callback.message, RAMS_PHOTOS_DIR)
    kb = _inline(
        ("🔑 Узнать условия покупки", "rams_conditions"),
        ("⬅️ Назад в меню", "go_club_menu"),
    )
    await callback.message.answer(TEXTS["rams_card"], reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "rams_conditions")
async def rams_ask_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RamsFSM.payment)
    await state.update_data(direction="Rams City")
    kb = _inline(
        ("💵 100% оплата", "rams_pay_full"),
        ("🏦 Ипотека", "rams_pay_mortgage"),
        ("⏳ Рассрочка", "rams_pay_installment"),
        ("⬅️ Назад в меню", "go_club_menu"),
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
    await state.set_state(RamsFSM.readiness)
    kb = _inline(
        ("🔥 Готов к сделке прямо сейчас", "rams_ready_now"),
        ("⏰ В течение 1–3 месяцев", "rams_ready_soon"),
        ("🔍 Пока изучаю варианты", "rams_ready_later"),
        ("⬅️ Назад в меню", "go_club_menu"),
    )
    await callback.message.answer(TEXTS["rams_ask_readiness"], reply_markup=kb)
    await callback.answer()


@router.callback_query(RamsFSM.readiness, F.data.startswith("rams_ready_"))
async def rams_readiness_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    mapping = {
        "rams_ready_now":   "Готов к сделке прямо сейчас",
        "rams_ready_soon":  "В течение 1–3 месяцев",
        "rams_ready_later": "Пока изучаю варианты",
    }
    await state.update_data(**{"Готовность к сделке": mapping[callback.data]})
    await state.set_state(RamsFSM.phone)
    await callback.message.answer(
        TEXTS["rams_ask_phone"], reply_markup=_share_contact_kb(),
    )
    await callback.answer()


@router.message(RamsFSM.phone, F.contact)
async def rams_phone_received(message: Message, state: FSMContext) -> None:
    await _finalize_lead(message, state, direction="Rams City")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. ВЕТКА 3 — MASERATI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.callback_query(F.data == "priv_maserati")
async def show_maserati(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _send_photos(callback.message, MASERATI_PHOTOS_DIR)
    kb = _inline(
        ("🏁 Записаться на тест-драйв / Осмотр", "mas_testdrive"),
        ("⬅️ Назад в меню", "go_club_menu"),
    )
    await callback.message.answer(TEXTS["maserati_card"], reply_markup=kb)
    await callback.answer()


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
    await _handle_calendar(
        callback, state, "mascal",
        MaseratiFSM.meet_time, "maserati_ask_time",
        lambda: _time_slots_kb("mas"),
    )


@router.message(MaseratiFSM.meet_date)
async def mas_date_fallback(message: Message) -> None:
    await message.answer("⚠️ Выберите дату из календаря выше.")


@router.callback_query(MaseratiFSM.meet_time, F.data.startswith("mas_time_"))
async def mas_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.replace("mas_time_", "")
    time_val = TIME_LABELS.get(key, key)
    await state.update_data(**{"Время встречи": time_val})
    await state.set_state(MaseratiFSM.payment)
    await callback.message.edit_text(f"🕐 Время: <b>{time_val}</b>")
    kb = _inline(
        ("💵 Наличный расчёт", "mas_pay_cash"),
        ("🏦 Автокредит", "mas_pay_credit"),
        ("🔄 Обмен (Trade-In)", "mas_pay_trade"),
        ("⬅️ Назад в меню", "go_club_menu"),
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
        TEXTS["maserati_ask_phone"], reply_markup=_share_contact_kb(),
    )
    await callback.answer()


@router.message(MaseratiFSM.phone, F.contact)
async def mas_phone_received(message: Message, state: FSMContext) -> None:
    await _finalize_lead(message, state, direction="Maserati")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. FALLBACK ОБРАБОТЧИКИ
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
    if current and current.startswith("AuthFSM"):
        await message.answer(TEXTS["contact_required"], reply_markup=AUTH_KB)
    elif current:
        await message.answer(TEXTS["not_understood"])
    else:
        # Нет состояния — отправляем к старту
        await message.answer(
            "Нажмите /start для начала работы.",
            reply_markup=ReplyKeyboardRemove(),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15. ТОЧКА ВХОДА
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
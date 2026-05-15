import asyncio
import json
import os
import sqlite3
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.markdown import hcode, html_decoration


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

API_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "1641958543"))
DB_PATH = os.getenv("DB_PATH", "bot_messages.db")

if not API_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN. Укажите токен бота в .env или переменной BOT_TOKEN.")


DEFAULT_SETTINGS = {
    "sent_emoji_id": "5870984130560266604",
    "sent_emoji_text": "💬",
    "confirm_emoji_id": "6030848053177486888",
    "confirm_emoji_text": "❓",
    "yes_button_emoji_id": "5870633910337015697",
    "yes_button_emoji_text": "✅",
    "no_button_emoji_id": "5870657884844462243",
    "no_button_emoji_text": "❌",
    "answer_emoji_id": "6030622631818956594",
    "answer_emoji_text": "💬",
    "start_ru_emoji_id": "5472055112702629499",
    "start_ru_emoji_text": "👋",
    "blocked_emoji_id": "5240241223632954241",
    "blocked_emoji_text": "🚫",
    "admin_ban_emoji_id": "5240241223632954241",
    "admin_ban_emoji_text": "🚫",
    "admin_unban_emoji_id": "5206607081334906820",
    "admin_unban_emoji_text": "✔️",
    "english_button_emoji_id": "5202021044105257611",
    "english_button_emoji_text": "🇺🇸",
    "russian_button_emoji_id": "5449408995691341691",
    "russian_button_emoji_text": "🇷🇺",
}


bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS message_links (
        owner_message_id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        user_message_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS pending_messages (
        user_id INTEGER PRIMARY KEY,
        data TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS user_languages (
        user_id INTEGER PRIMARY KEY,
        language TEXT NOT NULL
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        full_name TEXT
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS banned_users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)
conn.commit()


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    cursor.execute(query, params)
    conn.commit()


def fetchone(query: str, params: tuple[Any, ...] = ()) -> tuple | None:
    cursor.execute(query, params)
    return cursor.fetchone()


def save_message_link(owner_message_id: int, user_id: int, user_message_id: int | None) -> None:
    execute(
        """
        INSERT OR REPLACE INTO message_links (owner_message_id, user_id, user_message_id)
        VALUES (?, ?, ?)
        """,
        (owner_message_id, user_id, user_message_id),
    )


def get_user_by_owner_message(owner_message_id: int) -> int | None:
    row = fetchone("SELECT user_id FROM message_links WHERE owner_message_id = ?", (owner_message_id,))
    return int(row[0]) if row else None


def set_setting(key: str, value: str) -> None:
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_setting(key: str) -> str | None:
    row = fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    return str(row[0]) if row else DEFAULT_SETTINGS.get(key)


def set_user_language(user_id: int, language: str) -> None:
    execute(
        "INSERT OR REPLACE INTO user_languages (user_id, language) VALUES (?, ?)",
        (user_id, language),
    )


def get_user_language(user_id: int) -> str:
    row = fetchone("SELECT language FROM user_languages WHERE user_id = ?", (user_id,))
    return str(row[0]) if row else "ru"


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def remember_user(message: Message) -> None:
    if not message.from_user:
        return

    username = normalize_username(message.from_user.username) if message.from_user.username else None
    execute(
        """
        INSERT OR REPLACE INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        """,
        (message.from_user.id, username, message.from_user.full_name),
    )


def find_user_id_by_username(username: str) -> int | None:
    normalized = normalize_username(username)
    row = fetchone("SELECT user_id FROM users WHERE username = ?", (normalized,))
    return int(row[0]) if row else None


def ban_user(user_id: int, username: str | None = None) -> None:
    execute(
        "INSERT OR REPLACE INTO banned_users (user_id, username) VALUES (?, ?)",
        (user_id, normalize_username(username) if username else None),
    )


def unban_user(user_id: int) -> None:
    execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))


def is_banned(user_id: int) -> bool:
    return fetchone("SELECT user_id FROM banned_users WHERE user_id = ?", (user_id,)) is not None


def save_pending_message(user_id: int, data: dict) -> None:
    execute(
        "INSERT OR REPLACE INTO pending_messages (user_id, data) VALUES (?, ?)",
        (user_id, json.dumps(data, ensure_ascii=False)),
    )


def pop_pending_message(user_id: int) -> dict | None:
    row = fetchone("SELECT data FROM pending_messages WHERE user_id = ?", (user_id,))
    execute("DELETE FROM pending_messages WHERE user_id = ?", (user_id,))
    return json.loads(row[0]) if row else None


def confirmation_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    yes_text = "Yes" if language == "en" else "Да"
    no_text = "No" if language == "en" else "Нет"
    yes_button = InlineKeyboardButton(text=yes_text, callback_data="confirm_send_yes")
    no_button = InlineKeyboardButton(text=no_text, callback_data="confirm_send_no")

    yes_emoji_id = get_setting("yes_button_emoji_id")
    no_emoji_id = get_setting("no_button_emoji_id")

    if yes_emoji_id:
        yes_button.icon_custom_emoji_id = yes_emoji_id
    if no_emoji_id:
        no_button.icon_custom_emoji_id = no_emoji_id

    return InlineKeyboardMarkup(inline_keyboard=[[yes_button, no_button]])


def start_language_keyboard() -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text="English", callback_data="start_lang_en")
    emoji_id = get_setting("english_button_emoji_id")
    if emoji_id:
        button.icon_custom_emoji_id = emoji_id

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button]
        ]
    )


def start_russian_keyboard() -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text="Русский", callback_data="start_lang_ru")
    emoji_id = get_setting("russian_button_emoji_id")
    if emoji_id:
        button.icon_custom_emoji_id = emoji_id

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button]
        ]
    )


def get_entity_type(entity) -> str:
    entity_type = getattr(entity, "type", "")
    return getattr(entity_type, "value", entity_type)


def slice_utf16(text: str, offset: int, length: int) -> str:
    encoded = text.encode("utf-16-le")
    return encoded[offset * 2 : (offset + length) * 2].decode("utf-16-le")


def extract_custom_emoji(message: Message) -> tuple[str, str] | None:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []

    for entity in entities:
        if get_entity_type(entity) == "custom_emoji" and entity.custom_emoji_id:
            return entity.custom_emoji_id, slice_utf16(text, entity.offset, entity.length) or "⭐"

    return None


def configured_custom_emoji(setting_prefix: str) -> str:
    emoji_id = get_setting(f"{setting_prefix}_emoji_id")
    emoji_text = get_setting(f"{setting_prefix}_emoji_text") or "⭐"

    if not emoji_id:
        return ""

    return f'<tg-emoji emoji-id="{emoji_id}">{html_decoration.quote(emoji_text)}</tg-emoji>'


def sent_confirmation_text(language: str = "ru") -> str:
    emoji = configured_custom_emoji("sent")
    text = "Message sent." if language == "en" else "Сообщение отправлено."
    return f"{emoji} {text}" if emoji else text


def send_question_text(language: str = "ru") -> str:
    emoji = configured_custom_emoji("confirm")
    text = "Send this message to the owner?" if language == "en" else "Отправить это сообщение владельцу?"
    return f"{emoji} {text}" if emoji else text


def sending_message_text(language: str = "ru") -> str:
    return "Sending message..." if language == "en" else "Отправляю сообщение..."


def blocked_text(user_id: int) -> str:
    emoji = configured_custom_emoji("blocked")
    text = "You are blocked" if get_user_language(user_id) == "en" else "Вы заблокированны"
    return f"{emoji} {text}" if emoji else text


def admin_ban_text(username: str) -> str:
    emoji = configured_custom_emoji("admin_ban")
    text = f"Пользователь @{normalize_username(username)} заблокирован."
    return f"{emoji} {text}" if emoji else text


def admin_unban_text(username: str) -> str:
    emoji = configured_custom_emoji("admin_unban")
    text = f"Пользователь @{normalize_username(username)} разблокирован."
    return f"{emoji} {text}" if emoji else text


def russian_start_text(username: str) -> str:
    emoji = configured_custom_emoji("start_ru")
    greeting = f"Здравствуй, {html_decoration.quote(username)}!\nНапиши мне то, что ты хочешь мне донести"
    return f"{emoji} {greeting}" if emoji else greeting


def english_start_text(username: str) -> str:
    emoji = configured_custom_emoji("start_ru")
    greeting = f"Hello, {html_decoration.quote(username)}!\nWrite me what you want to tell me"
    return f"{emoji} {greeting}" if emoji else greeting


def safe_html_caption(message: Message) -> str | None:
    if not message.caption:
        return None

    return html_decoration.quote(message.caption)


def build_payload(message: Message) -> dict:
    if message.text:
        return {"type": "text", "text": message.html_text}
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id, "caption": safe_html_caption(message)}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id, "caption": safe_html_caption(message)}
    if message.animation:
        return {"type": "animation", "file_id": message.animation.file_id, "caption": safe_html_caption(message)}
    if message.voice:
        return {"type": "voice", "file_id": message.voice.file_id, "caption": safe_html_caption(message)}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id, "caption": safe_html_caption(message)}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id, "caption": safe_html_caption(message)}
    if message.sticker:
        return {"type": "sticker", "file_id": message.sticker.file_id}
    if message.video_note:
        return {"type": "video_note", "file_id": message.video_note.file_id}
    return {"type": "unsupported"}


async def send_payload(chat_id: int, payload: dict) -> Message:
    payload_type = payload["type"]

    if payload_type == "text":
        return await bot.send_message(chat_id, payload["text"])

    caption = payload.get("caption")
    if caption and len(caption) > 1000:
        await bot.send_message(chat_id, caption)
        payload = payload.copy()
        payload["caption"] = None

    if payload_type == "photo":
        return await bot.send_photo(chat_id, payload["file_id"], caption=payload.get("caption"))
    if payload_type == "video":
        return await bot.send_video(chat_id, payload["file_id"], caption=payload.get("caption"))
    if payload_type == "animation":
        return await bot.send_animation(chat_id, payload["file_id"], caption=payload.get("caption"))
    if payload_type == "voice":
        return await bot.send_voice(chat_id, payload["file_id"], caption=payload.get("caption"))
    if payload_type == "audio":
        return await bot.send_audio(chat_id, payload["file_id"], caption=payload.get("caption"))
    if payload_type == "document":
        return await bot.send_document(chat_id, payload["file_id"], caption=payload.get("caption"))
    if payload_type == "sticker":
        return await bot.send_sticker(chat_id, payload["file_id"])
    if payload_type == "video_note":
        return await bot.send_video_note(chat_id, payload["file_id"])

    return await bot.send_message(chat_id, "Пользователь отправил тип сообщения, который бот пока не поддерживает.")


def with_answer_prefix(payload: dict, language: str = "ru") -> dict:
    prefixed = payload.copy()
    emoji = configured_custom_emoji("answer")
    answer_text = "Answer:" if language == "en" else "Ответ:"
    prefix = f"{emoji} <b>{answer_text}</b>" if emoji else f"<b>{answer_text}</b>"

    if prefixed["type"] == "text":
        prefixed["text"] = f"{prefix}\n{prefixed['text']}"
        return prefixed

    caption = prefixed.get("caption")
    prefixed["caption"] = f"{prefix}\n{caption}" if caption else prefix
    return prefixed


def with_owner_notification(payload: dict, user_info: dict) -> dict:
    prefixed = payload.copy()
    username = user_info.get("username") or "без username"
    user_id = user_info["id"]
    prefix = f"Новое сообщение от {html_decoration.quote(username)} ({hcode(str(user_id))})"

    if prefixed["type"] == "text":
        prefixed["text"] = f"{prefix}\n\n{prefixed['text']}"
        return prefixed

    if prefixed["type"] in {"sticker", "video_note"}:
        prefixed["owner_notification"] = prefix
        return prefixed

    caption = prefixed.get("caption")
    prefixed["caption"] = f"{prefix}\n\n{caption}" if caption else prefix
    return prefixed


async def send_user_message_to_owner(payload: dict, user_info: dict, user_message_id: int) -> None:
    header = None
    if payload.get("owner_notification"):
        header = await bot.send_message(OWNER_ID, payload["owner_notification"])

    sent = await send_payload(OWNER_ID, payload)
    user_id = user_info["id"]
    save_message_link(sent.message_id, user_id, user_message_id)

    if header:
        save_message_link(header.message_id, user_id, user_message_id)


@dp.message(Command("start"))
async def start(message: Message) -> None:
    remember_user(message)

    if message.from_user and is_banned(message.from_user.id):
        await message.answer(blocked_text(message.from_user.id))
        return

    if message.from_user and message.from_user.id == OWNER_ID:
        await message.answer(
            "Бот запущен. Когда пользователь напишет сюда, я сначала спрошу у него "
            "подтверждение, а потом пришлю сообщение тебе. Чтобы ответить пользователю, "
            "сделай reply на его сообщение."
        )
        return

    username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else message.from_user.full_name
    set_user_language(message.from_user.id, "ru")
    await message.answer(
        russian_start_text(username),
        reply_markup=start_language_keyboard(),
    )


@dp.callback_query(F.data == "start_lang_en")
async def start_lang_en(call: CallbackQuery) -> None:
    if is_banned(call.from_user.id):
        await call.answer(blocked_text(call.from_user.id), show_alert=True)
        return

    username = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    set_user_language(call.from_user.id, "en")
    await call.answer()
    await call.message.edit_text(
        english_start_text(username),
        reply_markup=start_russian_keyboard(),
    )


@dp.callback_query(F.data == "start_lang_ru")
async def start_lang_ru(call: CallbackQuery) -> None:
    if is_banned(call.from_user.id):
        await call.answer(blocked_text(call.from_user.id), show_alert=True)
        return

    username = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    set_user_language(call.from_user.id, "ru")
    await call.answer()
    await call.message.edit_text(
        russian_start_text(username),
        reply_markup=start_language_keyboard(),
    )


@dp.message(Command("setemoji"))
async def set_emoji(message: Message) -> None:
    remember_user(message)

    if not message.from_user or message.from_user.id != OWNER_ID:
        return

    parts = (message.text or "").split(maxsplit=2)
    emoji_slots = {
        "1": {"prefix": "sent", "description": "перед текстом «Сообщение отправлено.»", "preview": sent_confirmation_text},
        "2": {"prefix": "confirm", "description": "перед вопросом «Отправить это сообщение владельцу?»", "preview": send_question_text},
        "3": {"prefix": "yes_button", "description": "на кнопке «Да»", "preview": lambda: "Да"},
        "4": {"prefix": "no_button", "description": "на кнопке «Нет»", "preview": lambda: "Нет"},
        "5": {
            "prefix": "answer",
            "description": "перед текстом «Ответ:»",
            "preview": lambda: with_answer_prefix({"type": "text", "text": "Привет"})["text"],
        },
        "6": {
            "prefix": "start_ru",
            "description": "перед приветствием «Здравствуй...»",
            "preview": lambda: russian_start_text("@username"),
        },
        "7": {
            "prefix": "blocked",
            "description": "перед сообщением «Вы заблокированны»",
            "preview": lambda: blocked_text(0),
        },
        "8": {
            "prefix": "admin_ban",
            "description": "перед админ-сообщением «Пользователь заблокирован»",
            "preview": lambda: admin_ban_text("@username"),
        },
        "9": {
            "prefix": "admin_unban",
            "description": "перед админ-сообщением «Пользователь разблокирован»",
            "preview": lambda: admin_unban_text("@username"),
        },
        "10": {
            "prefix": "english_button",
            "description": "на кнопке «English»",
            "preview": lambda: "English",
        },
        "11": {
            "prefix": "russian_button",
            "description": "на кнопке «Русский»",
            "preview": lambda: "Русский",
        },
    }

    if len(parts) < 2 or parts[1] not in emoji_slots:
        await message.answer(
            "Использование:\n"
            "/setemoji 1 премиум-эмодзи - перед «Сообщение отправлено.»\n"
            "/setemoji 2 премиум-эмодзи - перед «Отправить это сообщение владельцу?»\n"
            "/setemoji 3 премиум-эмодзи - на кнопке «Да»\n"
            "/setemoji 4 премиум-эмодзи - на кнопке «Нет»\n"
            "/setemoji 5 премиум-эмодзи - перед «Ответ:»\n"
            "/setemoji 6 премиум-эмодзи - перед «Здравствуй...»\n"
            "/setemoji 7 премиум-эмодзи - перед «Вы заблокированны»\n"
            "/setemoji 8 премиум-эмодзи - перед «Пользователь заблокирован»\n"
            "/setemoji 9 премиум-эмодзи - перед «Пользователь разблокирован»\n"
            "/setemoji 10 премиум-эмодзи - на кнопке «English»\n"
            "/setemoji 11 премиум-эмодзи - на кнопке «Русский»"
        )
        return

    emoji = extract_custom_emoji(message.reply_to_message or message)
    if not emoji:
        await message.answer(
            f"Не нашел премиум-эмодзи. Отправь так: /setemoji {parts[1]} и сразу после номера вставь нужный эмодзи."
        )
        return

    slot = emoji_slots[parts[1]]
    emoji_id, emoji_text = emoji
    set_setting(f"{slot['prefix']}_emoji_id", emoji_id)
    set_setting(f"{slot['prefix']}_emoji_text", emoji_text)
    await message.answer(
        f"Готово, эмодзи #{parts[1]} теперь стоит {slot['description']}:\n{slot['preview']()}"
    )


@dp.message(Command("ban"))
async def ban_command(message: Message) -> None:
    remember_user(message)

    if not message.from_user or message.from_user.id != OWNER_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /ban @username")
        return

    username = parts[1].strip()
    target_user_id = find_user_id_by_username(username)
    if target_user_id is None:
        await message.answer("Я еще не знаю такого пользователя. Он должен хотя бы раз написать боту.")
        return

    ban_user(target_user_id, username)
    await message.answer(admin_ban_text(username))


@dp.message(Command("unban"))
async def unban_command(message: Message) -> None:
    remember_user(message)

    if not message.from_user or message.from_user.id != OWNER_ID:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /unban @username")
        return

    username = parts[1].strip()
    target_user_id = find_user_id_by_username(username)
    if target_user_id is None:
        await message.answer("Я еще не знаю такого пользователя. Он должен хотя бы раз написать боту.")
        return

    unban_user(target_user_id)
    await message.answer(admin_unban_text(username))


@dp.message(F.from_user.id == OWNER_ID)
async def handle_owner_message(message: Message) -> None:
    remember_user(message)

    if not message.reply_to_message:
        await message.answer("Чтобы ответить пользователю, сделайте reply на его сообщение.")
        return

    target_user_id = get_user_by_owner_message(message.reply_to_message.message_id)
    if target_user_id is None:
        await message.answer("Не нашел пользователя для этого сообщения.")
        return

    try:
        await send_payload(target_user_id, with_answer_prefix(build_payload(message), get_user_language(target_user_id)))
        await message.answer("Ответ отправлен.")
    except Exception as exc:
        await message.answer(f"Не удалось отправить ответ: {hcode(str(exc))}")


@dp.callback_query(F.data == "confirm_send_yes")
async def confirm_send_yes(call: CallbackQuery) -> None:
    uid = call.from_user.id

    if is_banned(uid):
        pop_pending_message(uid)
        text = blocked_text(uid)
        await call.answer(text, show_alert=True)
        await call.message.edit_text(text)
        return

    pending = pop_pending_message(uid)

    if pending is None:
        await call.answer("Сообщение уже не найдено.", show_alert=True)
        return

    language = get_user_language(uid)
    await call.answer()
    await call.message.edit_text(sending_message_text(language))

    try:
        payload = with_owner_notification(pending["payload"], pending["user_info"])
        await send_user_message_to_owner(payload, pending["user_info"], pending["message_id"])
        await call.message.edit_text(sent_confirmation_text(language))
    except Exception as exc:
        await call.message.edit_text(f"Не удалось отправить сообщение: {hcode(str(exc))}")


@dp.callback_query(F.data == "confirm_send_no")
async def confirm_send_no(call: CallbackQuery) -> None:
    if is_banned(call.from_user.id):
        pop_pending_message(call.from_user.id)
        text = blocked_text(call.from_user.id)
        await call.answer(text, show_alert=True)
        await call.message.edit_text(text)
        return

    pop_pending_message(call.from_user.id)
    await call.answer()
    await call.message.edit_text("Хорошо, сообщение не отправлено.")


@dp.message()
async def handle_user_message(message: Message) -> None:
    remember_user(message)

    if message.from_user is None or message.from_user.is_bot:
        return

    if is_banned(message.from_user.id):
        await message.answer(blocked_text(message.from_user.id))
        return

    uid = message.from_user.id
    save_pending_message(
        uid,
        {
            "message_id": message.message_id,
            "payload": build_payload(message),
            "user_info": {
                "id": uid,
                "username": f"@{message.from_user.username}" if message.from_user.username else None,
            },
        },
    )

    language = get_user_language(uid)
    await message.answer(send_question_text(language), reply_markup=confirmation_keyboard(language))


async def main() -> None:
    me = await bot.get_me()
    print(f"Бот запущен как @{me.username} (ID: {me.id})")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

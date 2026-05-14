import json
import os
import sqlite3
import tempfile
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
DATABASE_URL = os.getenv("DATABASE_URL")

if not API_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN. Укажите токен бота в переменной окружения BOT_TOKEN.")


bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


class Storage:
    def __init__(self) -> None:
        self.is_postgres = bool(DATABASE_URL)
        if self.is_postgres:
            import psycopg

            self.conn = psycopg.connect(DATABASE_URL)
        else:
            db_path = DB_PATH
            if os.getenv("VERCEL") and not os.path.isabs(db_path):
                db_path = os.path.join(tempfile.gettempdir(), db_path)

            self.conn = sqlite3.connect(db_path, check_same_thread=False)

        self.init_schema()

    def sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.is_postgres else query

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        cursor = self.conn.cursor()
        cursor.execute(self.sql(query), params)
        self.conn.commit()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> tuple | None:
        cursor = self.conn.cursor()
        cursor.execute(self.sql(query), params)
        return cursor.fetchone()

    def init_schema(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS message_links (
                owner_message_id INTEGER PRIMARY KEY,
                user_id BIGINT NOT NULL,
                user_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_messages (
                user_id BIGINT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


storage = Storage()


def save_message_link(owner_message_id: int, user_id: int, user_message_id: int | None) -> None:
    storage.execute(
        """
        INSERT INTO message_links (owner_message_id, user_id, user_message_id)
        VALUES (?, ?, ?)
        ON CONFLICT(owner_message_id) DO UPDATE SET
            user_id = excluded.user_id,
            user_message_id = excluded.user_message_id
        """,
        (owner_message_id, user_id, user_message_id),
    )


def get_user_by_owner_message(owner_message_id: int) -> int | None:
    row = storage.fetchone(
        "SELECT user_id FROM message_links WHERE owner_message_id = ?",
        (owner_message_id,),
    )
    return int(row[0]) if row else None


def set_setting(key: str, value: str) -> None:
    storage.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def get_setting(key: str) -> str | None:
    row = storage.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    return str(row[0]) if row else None


def save_pending_message(user_id: int, data: dict) -> None:
    storage.execute(
        """
        INSERT INTO pending_messages (user_id, data)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET data = excluded.data
        """,
        (user_id, json.dumps(data, ensure_ascii=False)),
    )


def pop_pending_message(user_id: int) -> dict | None:
    row = storage.fetchone("SELECT data FROM pending_messages WHERE user_id = ?", (user_id,))
    storage.execute("DELETE FROM pending_messages WHERE user_id = ?", (user_id,))
    return json.loads(row[0]) if row else None


def confirmation_keyboard() -> InlineKeyboardMarkup:
    yes_button = InlineKeyboardButton(text="Да", callback_data="confirm_send_yes")
    no_button = InlineKeyboardButton(text="Нет", callback_data="confirm_send_no")

    yes_emoji_id = get_setting("yes_button_emoji_id")
    no_emoji_id = get_setting("no_button_emoji_id")

    if yes_emoji_id:
        yes_button.icon_custom_emoji_id = yes_emoji_id
    if no_emoji_id:
        no_button.icon_custom_emoji_id = no_emoji_id

    return InlineKeyboardMarkup(inline_keyboard=[[yes_button, no_button]])


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


def sent_confirmation_text() -> str:
    emoji = configured_custom_emoji("sent")
    return f"{emoji} Сообщение отправлено." if emoji else "Сообщение отправлено."


def send_question_text() -> str:
    emoji = configured_custom_emoji("confirm")
    text = "Отправить это сообщение владельцу?"
    return f"{emoji} {text}" if emoji else text


def build_payload(message: Message) -> dict:
    if message.text:
        return {"type": "text", "text": message.html_text}
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.html_caption}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id, "caption": message.html_caption}
    if message.animation:
        return {"type": "animation", "file_id": message.animation.file_id, "caption": message.html_caption}
    if message.voice:
        return {"type": "voice", "file_id": message.voice.file_id, "caption": message.html_caption}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id, "caption": message.html_caption}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id, "caption": message.html_caption}
    if message.sticker:
        return {"type": "sticker", "file_id": message.sticker.file_id}
    if message.video_note:
        return {"type": "video_note", "file_id": message.video_note.file_id}
    return {"type": "unsupported"}


async def send_payload(chat_id: int, payload: dict) -> Message:
    payload_type = payload["type"]

    if payload_type == "text":
        return await bot.send_message(chat_id, payload["text"])
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


def with_answer_prefix(payload: dict) -> dict:
    prefixed = payload.copy()
    emoji = configured_custom_emoji("answer")
    prefix = f"{emoji} <b>Ответ:</b>" if emoji else "<b>Ответ:</b>"

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
    if message.from_user and message.from_user.id == OWNER_ID:
        await message.answer(
            "Бот запущен. Когда пользователь напишет сюда, я сначала спрошу у него "
            "подтверждение, а потом пришлю сообщение тебе. Чтобы ответить пользователю, "
            "сделай reply на его сообщение."
        )
        return

    await message.answer("Здравствуйте! Напишите сообщение, и я передам его владельцу после подтверждения.")


@dp.message(Command("setemoji"))
async def set_emoji(message: Message) -> None:
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
    }

    if len(parts) < 2 or parts[1] not in emoji_slots:
        await message.answer(
            "Использование:\n"
            "/setemoji 1 премиум-эмодзи - перед «Сообщение отправлено.»\n"
            "/setemoji 2 премиум-эмодзи - перед «Отправить это сообщение владельцу?»\n"
            "/setemoji 3 премиум-эмодзи - на кнопке «Да»\n"
            "/setemoji 4 премиум-эмодзи - на кнопке «Нет»\n"
            "/setemoji 5 премиум-эмодзи - перед «Ответ:»"
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


@dp.message(F.from_user.id == OWNER_ID)
async def handle_owner_message(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("Чтобы ответить пользователю, сделайте reply на его сообщение.")
        return

    target_user_id = get_user_by_owner_message(message.reply_to_message.message_id)
    if target_user_id is None:
        await message.answer("Не нашел пользователя для этого сообщения.")
        return

    try:
        await send_payload(target_user_id, with_answer_prefix(build_payload(message)))
        await message.answer("Ответ отправлен.")
    except Exception as exc:
        await message.answer(f"Не удалось отправить ответ: {hcode(str(exc))}")


@dp.callback_query(F.data == "confirm_send_yes")
async def confirm_send_yes(call: CallbackQuery) -> None:
    uid = call.from_user.id
    pending = pop_pending_message(uid)

    if pending is None:
        await call.answer("Сообщение уже не найдено.", show_alert=True)
        return

    await call.answer()
    await call.message.edit_text("Отправляю сообщение...")

    try:
        payload = with_owner_notification(pending["payload"], pending["user_info"])
        await send_user_message_to_owner(payload, pending["user_info"], pending["message_id"])
        await call.message.edit_text(sent_confirmation_text())
    except Exception as exc:
        await call.message.edit_text(f"Не удалось отправить сообщение: {hcode(str(exc))}")


@dp.callback_query(F.data == "confirm_send_no")
async def confirm_send_no(call: CallbackQuery) -> None:
    pop_pending_message(call.from_user.id)
    await call.answer()
    await call.message.edit_text("Хорошо, сообщение не отправлено.")


@dp.message()
async def handle_user_message(message: Message) -> None:
    if message.from_user is None or message.from_user.is_bot:
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

    await message.answer(send_question_text(), reply_markup=confirmation_keyboard())

import asyncio
import json
import traceback
from http.server import BaseHTTPRequestHandler

from aiogram.types import Update

from bot_core import bot, dp


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Telegram bot webhook is running.".encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            update = Update.model_validate(json.loads(raw_body))
            asyncio.run(dp.feed_update(bot, update))
        except Exception as exc:
            traceback.print_exc()
            body = {"ok": False, "error": str(exc)}
        else:
            body = {"ok": True}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

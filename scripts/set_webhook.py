import json
import os
import urllib.parse
import urllib.request


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

token = os.getenv("BOT_TOKEN")
webhook_url = os.getenv("WEBHOOK_URL")

if not token:
    raise RuntimeError("Не задан BOT_TOKEN.")

if not webhook_url:
    raise RuntimeError("Не задан WEBHOOK_URL. Пример: https://your-project.vercel.app/api/webhook")

api_url = f"https://api.telegram.org/bot{token}/setWebhook"
body = urllib.parse.urlencode({"url": webhook_url}).encode("utf-8")

request = urllib.request.Request(api_url, data=body, method="POST")
with urllib.request.urlopen(request, timeout=30) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), ensure_ascii=False, indent=2))

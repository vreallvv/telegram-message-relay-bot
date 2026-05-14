# Telegram Message Relay Bot

Бот принимает сообщения от пользователей, спрашивает подтверждение отправки и передает сообщение владельцу. Владелец отвечает пользователю через reply на полученное сообщение.

## Возможности

- подтверждение отправки через кнопки `Да` / `Нет`;
- скрытая передача сообщений без Telegram-пересылки от пользователя;
- ответы пользователю в формате `<b>Ответ:</b>`;
- premium emoji через команду `/setemoji`;
- локальный запуск через polling;
- запуск на Vercel через Telegram webhook.

## Emoji Slots

Команда доступна владельцу бота:

```text
/setemoji 1 emoji - перед «Сообщение отправлено.»
/setemoji 2 emoji - перед «Отправить это сообщение владельцу?»
/setemoji 3 emoji - на кнопке «Да»
/setemoji 4 emoji - на кнопке «Нет»
/setemoji 5 emoji - перед «Ответ:»
```

## Local Run

Создайте `.env` по примеру `.env.example`:

```env
BOT_TOKEN=your_token
OWNER_ID=1641958543
DB_PATH=bot_messages.db
```

Установите зависимости и запустите:

```powershell
pip install -r requirements.txt
python main.py
```

## Vercel Deploy

На Vercel добавьте Environment Variables:

```env
BOT_TOKEN=your_token
OWNER_ID=1641958543
DATABASE_URL=postgresql://...
```

Для Vercel нужна внешняя PostgreSQL-база: Neon, Supabase, Vercel Postgres или аналог. Локальный SQLite-файл не подходит для постоянного хранения на serverless-хостинге.

После деплоя установите webhook:

```powershell
$env:WEBHOOK_URL="https://your-project.vercel.app/api/webhook"
python .\scripts\set_webhook.py
```

Когда бот работает на Vercel, не запускайте локальный `python main.py`, иначе polling и webhook будут конфликтовать.

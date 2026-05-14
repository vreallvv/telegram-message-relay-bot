# Telegram Message Relay Bot

Бот принимает сообщения от пользователей, спрашивает подтверждение и передает сообщение владельцу. Владелец отвечает пользователю через reply.

## Запуск На BotHost

Переменные окружения:

```env
BOT_TOKEN=токен_бота_из_BotFather
OWNER_ID=1641958543
DB_PATH=bot_messages.db
```

Команда запуска:

```bash
python main.py
```

Файл зависимостей:

```bash
pip install -r requirements.txt
```

Если BotHost просит выбрать главный файл, укажите:

```text
main.py
```

Бот работает через polling, поэтому webhook в Telegram не нужен.

## Команды Владельца

```text
/setemoji 1 premium_emoji - перед «Сообщение отправлено.»
/setemoji 2 premium_emoji - перед «Отправить это сообщение владельцу?»
/setemoji 3 premium_emoji - на кнопке «Да»
/setemoji 4 premium_emoji - на кнопке «Нет»
/setemoji 5 premium_emoji - перед «Ответ:»
/setemoji 6 premium_emoji - перед приветствием
/setemoji 7 premium_emoji - перед сообщением блокировки
/setemoji 8 premium_emoji - перед админ-сообщением бана
/setemoji 9 premium_emoji - перед админ-сообщением разбана
/ban @username
/unban @username
```

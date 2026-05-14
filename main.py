import asyncio

from bot_core import bot, dp


async def main() -> None:
    me = await bot.get_me()
    print(f"Бот запущен как @{me.username} (ID: {me.id})")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

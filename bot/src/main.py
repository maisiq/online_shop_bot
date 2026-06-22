from config import bot, dp
from init import init
from server import run_server


async def bot_polling() -> None:
    async with init():
        await dp.start_polling(bot)


if __name__ == "__main__":
    run_server()

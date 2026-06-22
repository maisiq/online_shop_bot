from aiohttp.web_app import Application
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from cart.router import router as cart_router
from config import Container, dp
from faq.router import router as faq_router
from handlers.start import router as start_router
from logs.config import setup_logger
from products.router import router as product_router
from tasks.promo import promote


async def init(app: Application | None = None):
    setup_logger(False)

    container = Container()
    await container.init_resources()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(promote, 'interval', minutes=.5,)
    scheduler.start()

    dp.include_router(start_router)
    dp.include_router(product_router)
    dp.include_router(cart_router)
    dp.include_router(faq_router)

    yield

    await dp.emit_shutdown()
    scheduler.shutdown()
    await container.shutdown_resources()
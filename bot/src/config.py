from os import getenv

from aiogram import Bot, Dispatcher
from db.config import get_repository, init_pool
from dependency_injector import containers, providers

_env_prefix = 'PAYMENTS_BOT_'

# App

DEBUG = getenv(_env_prefix + 'DEBUG', False)

# Bot

TOKEN = getenv(_env_prefix + 'BOT_TOKEN')
PAYMASTER_TOKEN = getenv(_env_prefix + 'PAYMASTER_TOKEN')

# DB

POSTGRES_CONNINFO = getenv(_env_prefix + 'POSTGRES_CONNINFO')

# Server

SERVER_HOST = getenv(_env_prefix + 'SERVER_HOST')
SERVER_PORT = getenv(_env_prefix + 'SERVER_PORT')


bot = Bot(token=TOKEN)
dp = Dispatcher()


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=[
            'handlers.start',
            'tasks.promo',
            'products.router',
        ],
    )

    pool = providers.Resource(init_pool)

    repository = providers.Factory(
        get_repository,
        pool=pool,
    )

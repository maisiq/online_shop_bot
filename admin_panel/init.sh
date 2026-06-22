#!/bin/bash

gunicorn -w "$PAYMENTS_ADMIN_SERVER_WORKERS" \
-k uvicorn.workers.UvicornWorker config.asgi:application \
--bind "$PAYMENTS_ADMIN_SERVER_HOST:$PAYMENTS_ADMIN_SERVER_PORT"
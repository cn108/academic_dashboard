#!/bin/sh
# Production entrypoint: bring the schema up to date, then hand over to the
# server command (Gunicorn unless overridden).
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
fi

exec "$@"

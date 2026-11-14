"""ASGI config — HTTP only; the API no longer exposes WebSockets."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "academic_dashboard.settings")

application = get_asgi_application()

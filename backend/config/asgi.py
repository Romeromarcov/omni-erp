"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import sys

from django.core.asgi import get_asgi_application

# Agregar la carpeta 'apps' y la raíz del backend al PYTHONPATH
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
apps_path = os.path.join(current_dir, "apps")
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if apps_path not in sys.path:
    sys.path.insert(0, apps_path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from apps.core.telemetry import init_telemetry  # noqa: E402  (requiere sys.path y DJANGO_SETTINGS_MODULE)

init_telemetry()

application = get_asgi_application()

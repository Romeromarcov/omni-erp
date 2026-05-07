"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import sys

# Agregar la carpeta 'apps' al PYTHONPATH
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
apps_path = os.path.join(current_dir, 'apps')
if apps_path not in sys.path:
    sys.path.insert(0, apps_path)

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()

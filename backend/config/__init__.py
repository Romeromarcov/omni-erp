# Este import hace que la app de Celery se cargue cuando Django arranca,
# garantizando que @shared_task use esta instancia y no una efímera.
from .celery import app as celery_app

__all__ = ("celery_app",)

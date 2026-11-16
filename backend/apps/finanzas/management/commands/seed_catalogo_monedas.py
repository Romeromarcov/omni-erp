"""Siembra el catálogo base de monedas (USD, VES, EUR, USDT). Idempotente y no destructivo.

Uso::

    python manage.py seed_catalogo_monedas

Se ejecuta en cada arranque del servicio web (``entrypoint.sh``) y desde ``seed_empresa_inicial``.
Crea las monedas que falten y completa solo los campos que sigan en su valor placeholder; nunca
pisa una edición. Ver ``apps/finanzas/catalogo_monedas.py``.
"""

from django.core.management.base import BaseCommand

from apps.finanzas.catalogo_monedas import sembrar_catalogo_monedas


class Command(BaseCommand):
    help = "Siembra el catálogo base de monedas (USD, VES, EUR, USDT). Idempotente."

    def handle(self, *args, **options):
        r = sembrar_catalogo_monedas()
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo de monedas: {len(r.creadas)} creada(s) {r.creadas}, "
                f"{len(r.completadas)} completada(s) {r.completadas}, "
                f"{len(r.sin_cambios)} sin cambios."
            )
        )

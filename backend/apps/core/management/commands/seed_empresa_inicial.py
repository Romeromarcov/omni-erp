"""
Plan 0 (piloto distribuidora) · Tarea 0.4 — Seed de empresa inicial para producción.

Crea de forma **idempotente** y **parametrizada** la estructura mínima para que
una empresa (p. ej. la distribuidora del piloto) empiece a operar:

    Empresa  →  Usuario admin  →  Sucursal  →  Caja física + Caja virtual

A diferencia de ``create_initial_data`` (datos demo de desarrollo con la
contraseña hardcodeada ``admin123``), este comando es apto para **producción**:

  * **No incrusta ningún secreto** (R-CODE-8): la contraseña del admin se toma de
    ``--admin-password`` o de la variable de entorno ``OMNI_SEED_ADMIN_PASSWORD``;
    si no se provee ninguna, se genera una aleatoria y se imprime **una sola vez**.
  * **Valida** la contraseña contra ``AUTH_PASSWORD_VALIDATORS``.
  * Es **idempotente**: relanzarlo no duplica ni pisa datos existentes (en
    particular, **nunca** cambia la contraseña de un admin ya creado).
  * Es **parametrizable** para cualquier empresa, no solo la demo.

Uso:
    python manage.py seed_empresa_inicial \\
        --nombre-legal "Distribuidora XYZ C.A." \\
        --rif "J-40123456-7" \\
        --admin-username admin_xyz \\
        --admin-email admin@xyz.com

    # contraseña vía entorno (recomendado para no dejarla en el historial del shell):
    OMNI_SEED_ADMIN_PASSWORD='...' python manage.py seed_empresa_inicial ...
"""

import os
import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Empresa, Sucursal, Usuarios
from apps.finanzas.models import Caja, CajaFisica, Moneda


class Command(BaseCommand):
    help = "Crea (idempotente) Empresa + admin + sucursal + caja para arranque de producción."

    def add_arguments(self, parser):
        parser.add_argument(
            "--nombre-legal", required=True, help="Razón social de la empresa."
        )
        parser.add_argument(
            "--rif",
            required=True,
            help="Identificador fiscal (RIF). Clave de idempotencia de la empresa.",
        )
        parser.add_argument("--nombre-comercial", default=None)
        parser.add_argument(
            "--email", default=None, help="Email de contacto de la empresa."
        )
        parser.add_argument("--admin-username", required=True)
        parser.add_argument("--admin-email", required=True)
        parser.add_argument(
            "--admin-password",
            default=None,
            help="Si se omite, se lee de OMNI_SEED_ADMIN_PASSWORD; si tampoco está, se genera una.",
        )
        parser.add_argument(
            "--es-superusuario-omni",
            action="store_true",
            help="Marca al admin como superusuario Omni (proveedor del software). Por defecto NO.",
        )
        parser.add_argument("--sucursal-nombre", default="Principal")
        parser.add_argument(
            "--codigo-sucursal",
            default=None,
            help="Código único global de sucursal (≤10). Por defecto se deriva del RIF.",
        )
        parser.add_argument(
            "--moneda-base",
            default="USD",
            help="Código ISO de la moneda base (se crea como pública si no existe).",
        )
        parser.add_argument("--caja-nombre", default="Caja Principal")

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _codigo_desde_rif(rif: str) -> str:
        """Deriva un código de sucursal (≤10, alfanumérico) a partir del RIF."""
        base = "".join(c for c in rif if c.isalnum()).upper()
        return ("S" + base)[:10] if base else "SUC01"

    def _resolver_password(self, opt_password):
        """Resuelve y valida la contraseña del admin. Devuelve (password, fue_generada)."""
        password = opt_password or os.environ.get("OMNI_SEED_ADMIN_PASSWORD")
        generada = False
        if not password:
            password = secrets.token_urlsafe(16)
            generada = True
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                "La contraseña del admin no cumple AUTH_PASSWORD_VALIDATORS: "
                + "; ".join(exc.messages)
            )
        return password, generada

    # ── handle ─────────────────────────────────────────────────────────────

    @transaction.atomic
    def handle(self, *args, **options):
        # Resolver la contraseña ANTES de tocar la BD: una contraseña inválida
        # debe abortar sin crear nada.
        password, generada = self._resolver_password(options["admin_password"])

        # 1. Moneda base (catálogo global compartido).
        moneda, _ = Moneda.objects.get_or_create(
            codigo_iso=options["moneda_base"].upper(),
            defaults={
                "nombre": options["moneda_base"].upper(),
                "simbolo": options["moneda_base"].upper()[:5],
                "es_publica": True,
            },
        )

        # 2. Empresa (idempotente por RIF).
        rif = options["rif"].strip()
        empresa, creada_empresa = Empresa.objects.get_or_create(
            identificador_fiscal=rif,
            defaults={
                "nombre_legal": options["nombre_legal"],
                "nombre_comercial": options["nombre_comercial"],
                "email_contacto": options["email"],
                "id_moneda_base": moneda,
                "activo": True,
            },
        )
        if not creada_empresa and empresa.id_moneda_base is None:
            empresa.id_moneda_base = moneda
            empresa.save(update_fields=["id_moneda_base"])

        # 3. Sucursal (idempotente por empresa + código).
        codigo_sucursal = (options["codigo_sucursal"] or self._codigo_desde_rif(rif))[
            :10
        ]
        sucursal, _ = Sucursal.objects.get_or_create(
            id_empresa=empresa,
            codigo_sucursal=codigo_sucursal,
            defaults={"nombre": options["sucursal_nombre"]},
        )

        # 4. Caja física + caja virtual (la operación de caja del piloto necesita ambas).
        caja_fisica, _ = CajaFisica.objects.get_or_create(
            empresa=empresa,
            nombre=options["caja_nombre"],
            defaults={
                "sucursal": sucursal,
                "tipo_caja": "REGISTRADORA",
                "identificador_dispositivo": f"SEED-{rif}-{options['caja_nombre']}"[
                    :100
                ],
            },
        )
        caja_virtual, _ = Caja.objects.get_or_create(
            empresa=empresa,
            nombre=options["caja_nombre"],
            caja_fisica=caja_fisica,
            defaults={
                "sucursal": sucursal,
                "tipo_caja": "REGISTRADORA",
                "moneda": moneda,
            },
        )

        # 5. Usuario admin.
        usuario, creado_usuario = Usuarios.objects.get_or_create(
            username=options["admin_username"],
            defaults={
                "email": options["admin_email"],
                "is_staff": True,
                "is_active": True,
                "es_superusuario_omni": options["es_superusuario_omni"],
            },
        )
        if creado_usuario:
            usuario.set_password(password)
            usuario.save(update_fields=["password"])
        usuario.empresas.add(empresa)
        usuario.sucursales.add(sucursal)
        if usuario.id_sucursal_predeterminada is None:
            usuario.id_sucursal_predeterminada = sucursal
            usuario.save(update_fields=["id_sucursal_predeterminada"])

        # ── Reporte ──────────────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS(
                f"Empresa : {empresa.nombre_legal} ({rif}) [{'creada' if creada_empresa else 'existente'}]"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"Sucursal: {sucursal.nombre} / {codigo_sucursal}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Caja    : {caja_virtual.nombre} ({moneda.codigo_iso})")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Admin   : {usuario.username} [{'creado' if creado_usuario else 'existente'}]"
                f"{' · superusuario_omni' if usuario.es_superusuario_omni else ''}"
            )
        )
        if creado_usuario and generada:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠ Contraseña generada para el admin (se muestra UNA sola vez, guárdala ya):\n"
                    f"    {password}\n"
                )
            )
        elif not creado_usuario:
            self.stdout.write(
                self.style.WARNING(
                    "El admin ya existía: su contraseña NO fue modificada."
                )
            )

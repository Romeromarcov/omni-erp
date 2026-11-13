"""Crea (idempotente) la cuenta de servicio de los bots de Telegram y registra a los vendedores.

La cuenta de servicio es un usuario NO staff de la empresa con el permiso ``bots_ingest.ingestar``.
No incrusta secretos (R-CODE-8): la contraseña sale de ``--password``, de la variable
``OMNI_BOT_PASSWORD`` o se genera aleatoria y se imprime una sola vez. Nunca cambia la contraseña
de un usuario ya existente.

Uso:
    python manage.py crear_usuario_bot --empresa-rif J-123456789 --username bot_lubrikca \\
        --vendedor 111222333=ana@lubrikca.com --vendedor 444555666=luis@lubrikca.com

``--vendedor ID_TELEGRAM=EMAIL_OMNI`` enlaza un usuario de Telegram con un usuario Omni existente
de la empresa (el vendedor que firma pedidos y comisiones).
"""

import os
import secrets

from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.bots_ingest.models import BotUsuario
from apps.core.models import Empresa, Usuarios


class Command(BaseCommand):
    help = "Crea la cuenta de servicio de los bots (permiso bots_ingest.ingestar) y registra vendedores de Telegram."

    def add_arguments(self, parser):
        parser.add_argument(
            "--empresa-rif", required=True, help="Identificador fiscal de la empresa."
        )
        parser.add_argument(
            "--username", required=True, help="Usuario de servicio (OMNI_USER del bot)."
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Contraseña; si falta usa OMNI_BOT_PASSWORD o genera una.",
        )
        parser.add_argument(
            "--vendedor",
            action="append",
            default=[],
            metavar="ID_TELEGRAM=EMAIL",
            help="Enlaza un usuario de Telegram con un usuario Omni de la empresa (repetible).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        empresa = Empresa.objects.filter(
            identificador_fiscal=opts["empresa_rif"]
        ).first()
        if empresa is None:
            raise CommandError(f"No existe una empresa con RIF {opts['empresa_rif']}.")

        pares = []
        for v in opts["vendedor"]:
            tid, sep, email = v.partition("=")
            if not (sep and tid.strip().isdigit() and email.strip()):
                raise CommandError(f"--vendedor inválido «{v}»: usa ID_TELEGRAM=EMAIL.")
            usuario = Usuarios.objects.filter(
                email__iexact=email.strip(), empresas=empresa, is_active=True
            ).first()
            if usuario is None:
                raise CommandError(
                    f"No hay un usuario activo de la empresa con email {email.strip()}."
                )
            pares.append((int(tid), usuario))

        bot = Usuarios.objects.filter(username=opts["username"]).first()
        if bot is not None and not bot.empresas.filter(pk=empresa.pk).exists():
            raise CommandError("Ese usuario existe y pertenece a otra empresa.")
        if bot is None:
            password = (
                opts["password"]
                or os.environ.get("OMNI_BOT_PASSWORD")
                or secrets.token_urlsafe(24)
            )
            try:
                validate_password(password)
            except ValidationError as e:
                raise CommandError("; ".join(e.messages)) from e
            bot = Usuarios(username=opts["username"], is_staff=False, is_active=True)
            bot.set_password(password)
            bot.save()
            bot.empresas.add(empresa)
            if not opts["password"] and not os.environ.get("OMNI_BOT_PASSWORD"):
                self.stdout.write(
                    self.style.WARNING(
                        f"Contraseña generada (guárdala, no se vuelve a mostrar): {password}"
                    )
                )
            self.stdout.write(
                self.style.SUCCESS(f"Usuario de servicio creado: {bot.username}")
            )
        else:
            self.stdout.write(
                f"Usuario de servicio ya existía: {bot.username} (contraseña intacta)"
            )

        perm = Permission.objects.get(
            codename="ingestar", content_type__app_label="bots_ingest"
        )
        bot.user_permissions.add(perm)

        for tid, usuario in pares:
            existente = BotUsuario.objects.filter(
                telegram_user_id=tid, activo=True
            ).first()
            if existente is not None and existente.id_empresa_id != empresa.pk:
                raise CommandError(
                    f"El usuario de Telegram {tid} ya está registrado en otra empresa."
                )
            BotUsuario.objects.update_or_create(
                id_empresa=empresa,
                telegram_user_id=tid,
                activo=True,
                defaults={
                    "usuario": usuario,
                    "nombre": usuario.get_full_name() or usuario.username,
                },
            )
            self.stdout.write(f"Telegram {tid} → {usuario.email}")

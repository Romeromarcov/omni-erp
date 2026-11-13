"""Comando crear_usuario_bot y selección de la instancia Odoo (misma que usa CxC Lubrikca)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.bots_ingest.models import BotUsuario
from apps.bots_ingest.services import odoo_push
from apps.core.models import Usuarios
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

pytestmark = [pytest.mark.django_db]

PW = "Xk9#vT2!qLm8@Zp4"


def correr(*args):
    out = StringIO()
    call_command("crear_usuario_bot", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def rif(empresa_a):
    return empresa_a.identificador_fiscal


def test_crea_cuenta_de_servicio_con_permiso_y_sin_staff(rif, user_a):
    correr(
        "--empresa-rif",
        rif,
        "--username",
        "bot1",
        "--password",
        PW,
        "--vendedor",
        f"111={user_a.email}",
    )
    bot = Usuarios.objects.get(username="bot1")
    assert (
        bot.check_password(PW)
        and not bot.is_staff
        and bot.has_perm("bots_ingest.ingestar")
    )
    assert BotUsuario.objects.get(telegram_user_id=111).usuario_id == user_a.pk


def test_es_idempotente_y_no_cambia_la_contrasena(rif, user_a):
    correr("--empresa-rif", rif, "--username", "bot1", "--password", PW)
    salida = correr(
        "--empresa-rif",
        rif,
        "--username",
        "bot1",
        "--password",
        "Otra#Clave9981x",
        "--vendedor",
        f"111={user_a.email}",
    )
    correr(
        "--empresa-rif", rif, "--username", "bot1", "--vendedor", f"111={user_a.email}"
    )
    assert (
        Usuarios.objects.get(username="bot1").check_password(PW) and "intacta" in salida
    )
    assert BotUsuario.objects.filter(telegram_user_id=111).count() == 1


def test_genera_contrasena_si_no_se_da(rif, monkeypatch):
    monkeypatch.delenv("OMNI_BOT_PASSWORD", raising=False)
    assert "Contraseña generada" in correr("--empresa-rif", rif, "--username", "bot2")


def test_toma_la_contrasena_del_entorno(rif, monkeypatch):
    monkeypatch.setenv("OMNI_BOT_PASSWORD", PW)
    salida = correr("--empresa-rif", rif, "--username", "bot3")
    assert Usuarios.objects.get(username="bot3").check_password(PW) and PW not in salida


@pytest.mark.parametrize(
    "args",
    [
        ["--empresa-rif", "J-0"],
        ["--vendedor", "abc=x@y.com"],
        ["--vendedor", "1=nadie@x.com"],
    ],
)
def test_errores_claros(rif, args):
    base = ["--empresa-rif", rif, "--username", "botx", "--password", PW]
    with pytest.raises(CommandError):
        call_command(
            "crear_usuario_bot",
            *(
                base + args
                if args[0] != "--empresa-rif"
                else ["--username", "botx"] + args
            ),
        )


def test_no_registra_telegram_de_otra_empresa(rif, user_a, user_b, empresa_b):
    BotUsuario.objects.create(
        id_empresa=empresa_b, telegram_user_id=222, usuario=user_b
    )
    with pytest.raises(CommandError, match="otra empresa"):
        correr(
            "--empresa-rif",
            rif,
            "--username",
            "bot1",
            "--password",
            PW,
            "--vendedor",
            f"222={user_a.email}",
        )


def test_contrasena_debil_se_rechaza(rif):
    with pytest.raises(CommandError):
        correr("--empresa-rif", rif, "--username", "bot4", "--password", "123")


def test_instancia_odoo_usa_la_misma_seleccion_que_cxc(empresa_a):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo", defaults={"nombre": "Odoo"}
    )
    vieja = ConectorInstancia.objects.create(
        id_empresa=empresa_a, id_proveedor=prov, nombre="vieja", estado="activo"
    )
    nueva = ConectorInstancia.objects.create(
        id_empresa=empresa_a, id_proveedor=prov, nombre="nueva", estado="configurando"
    )
    assert (
        odoo_push.instancia_odoo(empresa_a).pk == nueva.pk
    )  # más reciente con activo=True, como CxC
    nueva.activo = False
    nueva.save()
    assert odoo_push.instancia_odoo(empresa_a).pk == vieja.pk

"""Tests de la aprobación del cierre híbrido (Fase 3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.models import Roles, UsuarioRoles
from apps.cxc_lubrikca.models import EstadoBandeja
from apps.cxc_lubrikca.services.aprobacion import (
    CODIGO_TIPO,
    confirmar_cierre,
    proponer_cierre,
)
from apps.cxc_lubrikca.services.captura import VinculacionError, registrar_vinculacion
from apps.gestion_aprobaciones.models import FlujoAprobacion, TipoAprobacion
from apps.gestion_aprobaciones.services import AprobacionError
from tests.factories import UsuariosFactory

from . import helpers as h

pytestmark = pytest.mark.django_db


def _bandeja_candidata(empresa, usuario):
    """Crea una bandeja candidata a cierre (neto liquidado)."""
    pedido = h.crear_pedido(empresa)
    h.crear_linea(empresa, pedido)
    h.crear_precio(empresa, lista="4", precio="100")
    h.crear_metodo(empresa, tipo_tasa="N_A")
    h.crear_descuento(empresa)
    h.crear_recompra(empresa)
    h.cargar_tasas(empresa)
    pago = h.crear_pago(empresa, monto=Decimal("94"))
    registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("94"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=usuario,
    )
    pedido.refresh_from_db()
    return pedido.bandeja


def _flujo_con_rol(empresa):
    """Configura el flujo de aprobación con un rol aprobador (cualquier monto)."""
    tipo = TipoAprobacion.objects.create(
        id_empresa=empresa,
        codigo_tipo=CODIGO_TIPO,
        nombre_tipo="Cierre",
        modulo_origen="cxc_lubrikca",
        activo=True,
    )
    rol = Roles.objects.create(id_empresa=empresa, nombre_rol="Aprobador Cierre")
    FlujoAprobacion.objects.create(
        id_tipo_aprobacion=tipo,
        orden_etapa=1,
        nombre_etapa="Gerencia",
        rol_aprobador=rol,
    )
    return rol


def test_proponer_no_candidata_falla(empresa_a, user_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista=pedido.lista_precios, precio="100")
    from apps.cxc_lubrikca.services.bridge import recalcular_bandeja

    bandeja = recalcular_bandeja(pedido)
    assert bandeja.candidata_a_cierre is False
    with pytest.raises(VinculacionError, match="no es candidata"):
        proponer_cierre(bandeja, user_a)


def test_proponer_confirmar_aprobador_con_rol_aprueba(empresa_a, user_a):
    rol = _flujo_con_rol(empresa_a)
    aprobador = UsuariosFactory(username="aprob_a", empresa=empresa_a)
    UsuarioRoles.objects.create(id_usuario=aprobador, id_rol=rol)

    bandeja = _bandeja_candidata(empresa_a, user_a)
    solicitud = proponer_cierre(bandeja, user_a)
    assert solicitud is not None

    confirmar_cierre(bandeja, aprobador, aprobado=True)
    bandeja.refresh_from_db()
    assert bandeja.estado == EstadoBandeja.APROBADO
    assert bandeja.aprobado_por_id == aprobador.pk


def test_confirmar_usuario_sin_rol_es_rechazado(empresa_a, user_a):
    _flujo_con_rol(empresa_a)
    sin_rol = UsuariosFactory(username="no_aprob", empresa=empresa_a)

    bandeja = _bandeja_candidata(empresa_a, user_a)
    proponer_cierre(bandeja, user_a)

    with pytest.raises(AprobacionError, match="rol aprobador"):
        confirmar_cierre(bandeja, sin_rol, aprobado=True)
    bandeja.refresh_from_db()
    assert bandeja.estado == EstadoBandeja.CALCULADO


def test_confirmar_sin_solicitud_pendiente_falla(empresa_a, user_a):
    bandeja = _bandeja_candidata(empresa_a, user_a)
    with pytest.raises(VinculacionError, match="pendiente"):
        confirmar_cierre(bandeja, user_a, aprobado=True)


def test_proponer_sin_flujo_no_requiere_aprobacion(empresa_a, user_a):
    # Sin FlujoAprobacion configurado, crear_solicitud devuelve None.
    bandeja = _bandeja_candidata(empresa_a, user_a)
    assert proponer_cierre(bandeja, user_a) is None

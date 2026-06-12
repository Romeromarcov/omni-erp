"""
Bugs lote 4 — finanzas (hallazgos de las revisiones de los PRs #103/#106/#107).

1. ``SesionCajaFisica.crear_caja_virtual`` no existía y dos call sites lo
   invocaban (``CajaUsuarioViewSet.crear_caja_virtual`` y
   ``CajaVirtualAuto.crear_caja_virtual_en_sesion``) → AttributeError latente
   (mismo patrón del lote 3). Ahora delega en la creación REAL de cajas
   virtuales: ``Caja`` mono-moneda colgada de ``caja_fisica`` + M2M de métodos
   + asignación ``CajaVirtualUsuario``. Tests: feliz, errores de negocio y
   aislamiento (mensaje neutro para moneda/método ajeno — R-CODE-1).
2. PATCH a /sesiones-caja/{id}/ con ``estado`` podía "reabrir" una sesión
   CERRADA (estado writable). Ahora ``estado`` es read-only: las transiciones
   van SOLO por sus endpoints (abrir-sesion / cerrar).
3. Carrera de doble apertura concurrente: dos POST simultáneos sin sesión
   previa pasaban ambos el pre-chequeo y el perdedor moría con IntegrityError
   500 al golpear ``unique_sesion_abierta_por_caja``. Ahora savepoint +
   traducción a 400 de negocio (solo ESA violación; otra IntegrityError se
   re-lanza). El test golpea el constraint REAL simulando la ventana de
   carrera (el pre-chequeo no ve la sesión del otro request).
4. ``transferir-entre-cajas``: monto=0 numérico caía en el guard falsy con el
   mensaje genérico de "faltan parámetros" — ahora responde "mayor a cero";
   y las cajas virtuales desactivadas (``activa=False``) quedan excluidas de
   la transferencia (mover saldo a/desde una caja fuera de operación lo
   sacaría de los cierres y del libro por defecto).

Dinero siempre Decimal (R-CODE-4); aislamiento multi-tenant en cada endpoint
tocado (R-CODE-1).
"""
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.finanzas.models import (
    Caja,
    CajaUsuario,
    CajaVirtualUsuario,
    MetodoPago,
    Moneda,
    SesionCajaFisica,
)

pytestmark = pytest.mark.django_db

URL_SESIONES = "/api/finanzas/sesiones-caja/"
URL_ABRIR_SESION = "/api/finanzas/cajas-fisicas/{}/abrir-sesion/"
MSG_CARRERA = "Ya hay una sesión abierta para esta caja física"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def sesion_abierta_a(caja_fisica_a, user_a):
    return SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)


@pytest.fixture
def metodo_a(empresa_a, moneda_usd):
    metodo = MetodoPago.objects.create(
        nombre_metodo="Efectivo Lote4", tipo_metodo="EFECTIVO", empresa=empresa_a
    )
    metodo.monedas.add(moneda_usd)
    return metodo


def _caja_virtual(empresa, moneda, caja_fisica, nombre, saldo="0.00", activa=True):
    return Caja.objects.create(
        empresa=empresa,
        nombre=nombre,
        moneda=moneda,
        caja_fisica=caja_fisica,
        saldo_actual=Decimal(saldo),
        activa=activa,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Ítem 1 — SesionCajaFisica.crear_caja_virtual (creación real)
# ─────────────────────────────────────────────────────────────────────────────


class TestCrearCajaVirtualEnSesion:
    def test_feliz_crea_caja_real_con_metodos_y_asignacion(
        self, sesion_abierta_a, caja_fisica_a, empresa_a, moneda_usd, metodo_a, user_a
    ):
        caja = sesion_abierta_a.crear_caja_virtual(
            nombre="Pago Móvil USD",
            monedas_ids=[str(moneda_usd.id_moneda)],
            metodos_pago_ids=[str(metodo_a.id_metodo_pago)],
            usuario=user_a,
        )
        assert isinstance(caja, Caja)
        assert caja.empresa_id == empresa_a.pk
        assert caja.caja_fisica_id == caja_fisica_a.pk
        assert caja.moneda_id == moneda_usd.pk
        assert caja.saldo_actual == Decimal("0.00")  # R-CODE-4
        assert list(caja.metodos_pago.values_list("pk", flat=True)) == [metodo_a.pk]
        # Queda asignada al usuario por la vía real (CajaVirtualUsuario).
        assert CajaVirtualUsuario.objects.filter(usuario=user_a, caja_virtual=caja).exists()
        # Y cuelga de la relación real caja_fisica.cajas_virtuales.
        assert caja in caja_fisica_a.cajas_virtuales.all()

    def test_sesion_cerrada_valueerror(self, sesion_abierta_a, moneda_usd):
        sesion_abierta_a.cerrar_sesion()
        sesion_abierta_a.refresh_from_db()
        with pytest.raises(ValueError, match="sesión cerrada"):
            sesion_abierta_a.crear_caja_virtual(
                nombre="X", monedas_ids=[str(moneda_usd.id_moneda)]
            )

    def test_sin_nombre_valueerror(self, sesion_abierta_a, moneda_usd):
        with pytest.raises(ValueError, match="nombre"):
            sesion_abierta_a.crear_caja_virtual(
                nombre="   ", monedas_ids=[str(moneda_usd.id_moneda)]
            )

    def test_monedas_distinto_de_una_valueerror(self, sesion_abierta_a, moneda_usd):
        with pytest.raises(ValueError, match="exactamente una moneda"):
            sesion_abierta_a.crear_caja_virtual(nombre="X", monedas_ids=[])

    def test_moneda_de_otro_tenant_mensaje_neutro(self, sesion_abierta_a, empresa_b):
        """R-CODE-1: moneda ajena → mismo mensaje que inexistente."""
        moneda_b = Moneda.objects.create(
            nombre="Privada B", codigo_iso="PRB", simbolo="₱", tipo_moneda="fiat", empresa=empresa_b
        )
        with pytest.raises(ValueError, match="Moneda no encontrada o no disponible"):
            sesion_abierta_a.crear_caja_virtual(nombre="X", monedas_ids=[str(moneda_b.id_moneda)])

    def test_metodo_de_otro_tenant_o_inactivo_mensaje_neutro(
        self, sesion_abierta_a, moneda_usd, empresa_b, metodo_a
    ):
        metodo_b = MetodoPago.objects.create(
            nombre_metodo="Zelle B", tipo_metodo="ELECTRONICO", empresa=empresa_b
        )
        with pytest.raises(ValueError, match="Método de pago no encontrado o no disponible"):
            sesion_abierta_a.crear_caja_virtual(
                nombre="X",
                monedas_ids=[str(moneda_usd.id_moneda)],
                metodos_pago_ids=[str(metodo_b.id_metodo_pago)],
            )
        metodo_a.activo = False
        metodo_a.save(update_fields=["activo"])
        with pytest.raises(ValueError, match="Método de pago no encontrado o no disponible"):
            sesion_abierta_a.crear_caja_virtual(
                nombre="X",
                monedas_ids=[str(moneda_usd.id_moneda)],
                metodos_pago_ids=[str(metodo_a.id_metodo_pago)],
            )

    def test_caja_virtual_auto_delegacion_real(
        self, sesion_abierta_a, empresa_a, moneda_usd, metodo_a, user_a
    ):
        """CajaVirtualAuto.crear_caja_virtual_en_sesion (el otro call site del
        AttributeError latente) funciona contra la sesión REAL."""
        from apps.finanzas.models import CajaVirtualAuto, PlantillaMaestroCajasVirtuales

        plantilla = PlantillaMaestroCajasVirtuales.objects.create(
            empresa=empresa_a, nombre="Plantilla L4", moneda_base=moneda_usd
        )
        plantilla.metodos_pago_base.add(metodo_a)
        auto = CajaVirtualAuto.objects.create(
            caja_fisica=sesion_abierta_a.caja_fisica,
            plantilla_maestro=plantilla,
            moneda=moneda_usd,
            metodo_pago=metodo_a,
        )
        caja = auto.crear_caja_virtual_en_sesion(sesion_abierta_a)
        assert isinstance(caja, Caja)
        assert caja.moneda_id == moneda_usd.pk
        assert list(caja.metodos_pago.values_list("pk", flat=True)) == [metodo_a.pk]
        assert CajaVirtualUsuario.objects.filter(usuario=user_a, caja_virtual=caja).exists()


class TestCajaUsuarioCrearCajaVirtualEndpoint:
    """La acción crear-caja-virtual de CajaUsuarioViewSet (no enrutado) vía
    as_view: feliz + error + aislamiento."""

    def _post(self, user, pk, data):
        from apps.finanzas.views import CajaUsuarioViewSet

        view = CajaUsuarioViewSet.as_view({"post": "crear_caja_virtual"})
        request = APIRequestFactory().post(
            f"/finanzas/cajas-usuario-legacy/{pk}/crear-caja-virtual/", data, format="json"
        )
        force_authenticate(request, user=user)
        return view(request, pk=str(pk))

    @pytest.fixture
    def asignacion_a(self, user_a, empresa_a, moneda_usd, caja_fisica_a):
        caja = _caja_virtual(empresa_a, moneda_usd, caja_fisica_a, "Asignada A")
        return CajaUsuario.objects.create(usuario=user_a, caja=caja)

    def test_feliz_200_crea_caja(
        self, asignacion_a, sesion_abierta_a, user_a, moneda_usd, metodo_a
    ):
        resp = self._post(
            user_a,
            asignacion_a.pk,
            {
                "nombre": "Zelle mostrador",
                "monedas": [str(moneda_usd.id_moneda)],
                "metodos_pago": [str(metodo_a.id_metodo_pago)],
            },
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["mensaje"] == "Caja virtual 'Zelle mostrador' creada exitosamente"
        creada = Caja.objects.get(nombre="Zelle mostrador")
        assert str(creada.id_caja) == str(resp.data["caja_virtual"]["id_caja"])
        assert creada.caja_fisica_id == sesion_abierta_a.caja_fisica_id

    def test_sin_nombre_400(self, asignacion_a, sesion_abierta_a, user_a):
        resp = self._post(user_a, asignacion_a.pk, {})
        assert resp.status_code == 400
        assert resp.data == {"error": "Debe especificar un nombre para la caja virtual"}

    def test_moneda_ajena_400_neutro(self, asignacion_a, sesion_abierta_a, user_a, empresa_b):
        """R-CODE-1: la moneda privada de la empresa B no existe para A."""
        moneda_b = Moneda.objects.create(
            nombre="Privada B", codigo_iso="PRB", simbolo="₱", tipo_moneda="fiat", empresa=empresa_b
        )
        resp = self._post(
            user_a, asignacion_a.pk, {"nombre": "X", "monedas": [str(moneda_b.id_moneda)]}
        )
        assert resp.status_code == 400
        assert resp.data == {"error": "Moneda no encontrada o no disponible para la empresa."}
        assert not Caja.objects.filter(nombre="X").exists()

    def test_asignacion_de_otro_usuario_404(self, asignacion_a, sesion_abierta_a, user_b):
        resp = self._post(user_b, asignacion_a.pk, {"nombre": "Intrusa"})
        assert resp.status_code == 404
        assert not Caja.objects.filter(nombre="Intrusa").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Ítem 2 — PATCH no transiciona el estado de la sesión
# ─────────────────────────────────────────────────────────────────────────────


class TestPatchSesionNoCambiaEstado:
    def test_patch_no_reabre_sesion_cerrada(self, client_a, sesion_abierta_a):
        sesion_abierta_a.cerrar_sesion()
        resp = client_a.patch(
            f"{URL_SESIONES}{sesion_abierta_a.id_sesion}/",
            {"estado": "ABIERTA", "notas": "intento de reapertura"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        sesion_abierta_a.refresh_from_db()
        # estado read-only: DRF lo ignora; las notas (writable) sí cambian.
        assert sesion_abierta_a.estado == "CERRADA"
        assert resp.data["estado"] == "CERRADA"
        assert sesion_abierta_a.notas == "intento de reapertura"

    def test_patch_no_cierra_sesion_abierta(self, client_a, sesion_abierta_a):
        """Tampoco se 'cierra' por PATCH: cerrar va por su endpoint (cierres
        de cajas + fecha_cierre atómicos)."""
        resp = client_a.patch(
            f"{URL_SESIONES}{sesion_abierta_a.id_sesion}/",
            {"estado": "CERRADA"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        sesion_abierta_a.refresh_from_db()
        assert sesion_abierta_a.estado == "ABIERTA"
        assert sesion_abierta_a.fecha_cierre is None

    def test_patch_sesion_ajena_404(self, client_b, sesion_abierta_a):
        """R-CODE-1: la sesión de la empresa A no existe para B."""
        resp = client_b.patch(
            f"{URL_SESIONES}{sesion_abierta_a.id_sesion}/", {"notas": "x"}, format="json"
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Ítem 3 — carrera de doble apertura → 400 controlado (constraint real)
# ─────────────────────────────────────────────────────────────────────────────


def _simular_ventana_de_carrera():
    """Parchea el pre-chequeo de ``abrir_sesion`` para que NO vea la sesión
    abierta existente — exactamente lo que pasa cuando dos transacciones
    concurrentes leen antes de que la otra commitee. El INSERT posterior
    golpea la constraint parcial REAL ``unique_sesion_abierta_por_caja``."""
    return mock.patch.object(
        SesionCajaFisica.objects, "filter", return_value=SesionCajaFisica.objects.none()
    )


class TestCarreraDobleApertura:
    def test_post_sesiones_caja_concurrente_400(self, client_a, caja_fisica_a, sesion_abierta_a):
        with _simular_ventana_de_carrera():
            resp = client_a.post(
                URL_SESIONES,
                {"caja_fisica_principal": str(caja_fisica_a.id_caja_fisica)},
                format="json",
            )
        assert resp.status_code == 400, resp.data
        assert MSG_CARRERA in str(resp.data)
        # La sesión original sigue siendo la única abierta.
        assert SesionCajaFisica.objects.filter(estado="ABIERTA").count() == 1

    def test_abrir_sesion_action_concurrente_400(self, client_a, caja_fisica_a, sesion_abierta_a):
        with _simular_ventana_de_carrera():
            resp = client_a.post(URL_ABRIR_SESION.format(caja_fisica_a.id_caja_fisica), {})
        assert resp.status_code == 400, resp.data
        assert MSG_CARRERA in resp.data["error"]

    def test_servicio_traduce_solo_la_constraint_de_apertura(
        self, caja_fisica_a, user_a, sesion_abierta_a
    ):
        with _simular_ventana_de_carrera():
            with pytest.raises(ValueError, match=MSG_CARRERA):
                SesionCajaFisica.abrir_sesion(caja_fisica_a, user_a)

    def test_otra_integrityerror_se_relanza(self, caja_fisica_a):
        """usuario=None viola NOT NULL: NO debe disfrazarse de 'apertura
        simultánea' — se re-lanza tal cual (bug distinto)."""
        with pytest.raises(IntegrityError):
            SesionCajaFisica.abrir_sesion(caja_fisica_a, None)


# ─────────────────────────────────────────────────────────────────────────────
# Ítem 4 — transferir-entre-cajas: monto=0 y cajas desactivadas
# ─────────────────────────────────────────────────────────────────────────────


class TestTransferirMontoCeroYCajasInactivas:
    @pytest.fixture
    def cajas(self, empresa_a, moneda_usd, caja_fisica_a):
        origen = _caja_virtual(empresa_a, moneda_usd, caja_fisica_a, "Origen L4", saldo="100.00")
        destino = _caja_virtual(empresa_a, moneda_usd, caja_fisica_a, "Destino L4")
        return origen, destino

    def _post(self, client, sesion, origen, destino, monto):
        return client.post(
            f"{URL_SESIONES}{sesion.id_sesion}/transferir-entre-cajas/",
            {"caja_origen": str(origen.id_caja), "caja_destino": str(destino.id_caja), "monto": monto},
            format="json",
        )

    @pytest.mark.parametrize("monto", [0, "0", "0.00"])
    def test_monto_cero_responde_mayor_a_cero(self, client_a, sesion_abierta_a, cajas, monto):
        origen, destino = cajas
        resp = self._post(client_a, sesion_abierta_a, origen, destino, monto)
        assert resp.status_code == 400
        assert resp.json() == {"error": "El monto de la transferencia debe ser mayor a cero."}

    def test_monto_none_sigue_siendo_parametro_faltante(self, client_a, sesion_abierta_a, cajas):
        origen, destino = cajas
        resp = self._post(client_a, sesion_abierta_a, origen, destino, None)
        assert resp.status_code == 400
        assert resp.json() == {"error": "Debe indicar caja_origen, caja_destino y monto."}

    @pytest.mark.parametrize("inactiva", ["origen", "destino"])
    def test_caja_desactivada_excluida(self, client_a, sesion_abierta_a, cajas, inactiva):
        origen, destino = cajas
        caja = origen if inactiva == "origen" else destino
        caja.activa = False
        caja.save(update_fields=["activa"])
        resp = self._post(client_a, sesion_abierta_a, origen, destino, "10.00")
        assert resp.status_code == 400
        assert resp.json() == {
            "error": "No se puede transferir desde o hacia una caja virtual desactivada."
        }
        origen.refresh_from_db()
        destino.refresh_from_db()
        assert origen.saldo_actual == Decimal("100.00")
        assert destino.saldo_actual == Decimal("0.00")

    def test_feliz_sigue_funcionando(self, client_a, sesion_abierta_a, cajas):
        origen, destino = cajas
        resp = self._post(client_a, sesion_abierta_a, origen, destino, "25.50")
        assert resp.status_code == 200, resp.json()
        assert Decimal(resp.json()["monto"]) == Decimal("25.50")
        origen.refresh_from_db()
        destino.refresh_from_db()
        assert origen.saldo_actual == Decimal("74.50")
        assert destino.saldo_actual == Decimal("25.50")

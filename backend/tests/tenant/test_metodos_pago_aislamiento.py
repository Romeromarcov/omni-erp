"""
P0-1 — Aislamiento multi-tenant en métodos de pago (auditoría integral 2026-06-10).

Fija el comportamiento SEGURO de los hallazgos SEC-A1/A2/A3 y SEC-M2:

- SEC-A1: `MetodoPagoViewSet` ya no bypasea `get_queryset()` en `reutilizar`;
  operar un método PRIVADO de otra empresa por UUID → 404.
- SEC-A2: `reutilizar` valida la empresa destino contra `get_empresas_visible`;
  una empresa ajena → 404 y NO se crea nada en el tenant víctima.
- SEC-A3: `buscar_reutilizar` solo expone métodos `es_publico`/`es_generico`
  y proyecta campos no sensibles (sin `documento_json` ni `referencia_externa`).
- SEC-M2: `MetodoPagoEmpresaActivaSerializer` ignora la `empresa` del payload
  (read-only) e inyecta la del usuario; el FK `metodo_pago` solo acepta
  métodos visibles.

Convención del plan: aserciones con valores exactos (sirven de runner de mutación).
"""
import uuid

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import MetodoPago, MetodoPagoEmpresaActiva

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]

URL_METODOS = "/api/finanzas/metodos-pago/"
URL_ACTIVAS = "/api/finanzas/metodos-pago-empresa-activas/"


# ── Clients ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


# ── Fixtures de dominio ───────────────────────────────────────────────────────

@pytest.fixture
def metodo_privado_b(empresa_b):
    """Método PRIVADO de la empresa B con configuración sensible."""
    return MetodoPago.objects.create(
        nombre_metodo="Zelle Privado B",
        tipo_metodo="ELECTRONICO",
        empresa=empresa_b,
        referencia_externa="cuenta-secreta-b",
        documento_json={"api_key": "secreto-tenant-b"},
    )


@pytest.fixture
def metodo_publico(empresa_b):
    """Método público de B: reutilizable por diseño."""
    return MetodoPago.objects.create(
        nombre_metodo="Pago Móvil Público", tipo_metodo="ELECTRONICO",
        empresa=empresa_b, es_publico=True,
        documento_json={"banco": "0102"}, referencia_externa="ref-publica",
    )


@pytest.fixture
def metodo_generico(db):
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo Global", tipo_metodo="EFECTIVO", es_generico=True,
    )


# ── SEC-A1: IDOR por UUID en retrieve/reutilizar ─────────────────────────────

class TestIdorMetodoPagoAjeno:
    def test_get_metodo_privado_ajeno_404(self, client_a, metodo_privado_b):
        resp = client_a.get(f"{URL_METODOS}{metodo_privado_b.id_metodo_pago}/")
        assert resp.status_code == 404

    def test_reutilizar_metodo_privado_ajeno_404(self, client_a, empresa_a, metodo_privado_b):
        """Antes (override de get_object) esto copiaba documento_json ajeno → 201."""
        resp = client_a.post(
            f"{URL_METODOS}{metodo_privado_b.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(empresa_a.id_empresa)},
        )
        assert resp.status_code == 404
        # No se creó ninguna copia en la empresa A
        assert not MetodoPago.objects.filter(
            empresa=empresa_a, nombre_metodo="Zelle Privado B"
        ).exists()

    def test_patch_metodo_privado_ajeno_404(self, client_a, metodo_privado_b):
        resp = client_a.patch(
            f"{URL_METODOS}{metodo_privado_b.id_metodo_pago}/",
            {"nombre_metodo": "Hackeado"},
        )
        assert resp.status_code == 404
        metodo_privado_b.refresh_from_db()
        assert metodo_privado_b.nombre_metodo == "Zelle Privado B"


# ── SEC-A2: empresa destino fuera de las visibles ────────────────────────────

class TestReutilizarEmpresaDestino:
    def test_reutilizar_hacia_empresa_ajena_404(self, client_a, empresa_b, metodo_publico):
        # No requiere rapidfuzz: el 404 ocurre ANTES del matching fuzzy.
        antes = MetodoPago.objects.filter(empresa=empresa_b).count()
        resp = client_a.post(
            f"{URL_METODOS}{metodo_publico.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(empresa_b.id_empresa)},
        )
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Empresa no encontrada."}
        # No se inyectó nada en el tenant víctima
        assert MetodoPago.objects.filter(empresa=empresa_b).count() == antes

    def test_reutilizar_hacia_empresa_inexistente_404(self, client_a, metodo_publico):
        resp = client_a.post(
            f"{URL_METODOS}{metodo_publico.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_reutilizar_hacia_empresa_propia_201(self, client_a, empresa_a, metodo_publico):
        pytest.importorskip("rapidfuzz")  # dependencia opcional en el entorno dev
        resp = client_a.post(
            f"{URL_METODOS}{metodo_publico.id_metodo_pago}/reutilizar/",
            {"id_empresa": str(empresa_a.id_empresa)},
        )
        assert resp.status_code == 201, resp.content
        nuevo = MetodoPago.objects.get(empresa=empresa_a, nombre_metodo="Pago Móvil Público")
        assert nuevo.es_publico is False
        assert nuevo.es_generico is False

    def test_crear_metodo_con_empresa_ajena_400(self, client_a, empresa_b):
        """Creación directa: declarar empresa (ajena o no) sin ser superusuario → 400."""
        resp = client_a.post(URL_METODOS, {
            "nombre_metodo": "Intruso", "tipo_metodo": "OTRO",
            "empresa": str(empresa_b.id_empresa),
        })
        assert resp.status_code == 400
        assert not MetodoPago.objects.filter(empresa=empresa_b, nombre_metodo="Intruso").exists()


# ── SEC-A3: buscar_reutilizar no expone privados de terceros ─────────────────

class TestBuscarReutilizarProyeccion:
    def _results(self, resp):
        data = resp.json()
        return data["results"] if isinstance(data, dict) else data

    def test_no_lista_privados_de_terceros(
        self, client_a, metodo_privado_b, metodo_publico, metodo_generico
    ):
        resp = client_a.get(URL_METODOS + "buscar_reutilizar/")
        assert resp.status_code == 200
        results = self._results(resp)
        nombres = {m["nombre_metodo"] for m in results}
        # Los reutilizables por diseño sí aparecen (más los genéricos del seed
        # del conftest); el privado de B JAMÁS.
        assert {"Pago Móvil Público", "Efectivo Global"} <= nombres
        assert "Zelle Privado B" not in nombres
        # Verificación exacta contra BD: todo lo listado es público o genérico.
        for item in results:
            metodo = MetodoPago.objects.get(id_metodo_pago=item["id_metodo_pago"])
            assert metodo.es_publico is True or metodo.es_generico is True

    def test_no_expone_campos_sensibles(self, client_a, metodo_publico):
        resp = client_a.get(URL_METODOS + "buscar_reutilizar/")
        assert resp.status_code == 200
        results = self._results(resp)
        assert any(m["nombre_metodo"] == "Pago Móvil Público" for m in results)
        for item in results:
            assert set(item.keys()) == {
                "id_metodo_pago", "nombre_metodo", "tipo_metodo", "activo", "url", "aplicado"
            }
            assert "documento_json" not in item
            assert "referencia_externa" not in item
            assert "empresa" not in item

    def test_id_empresa_actual_ajena_404(self, client_a, empresa_b, metodo_generico):
        """La empresa "actual" debe ser visible: si no, sería un oráculo de nombres ajenos."""
        resp = client_a.get(
            URL_METODOS + "buscar_reutilizar/",
            {"id_empresa_actual": str(empresa_b.id_empresa)},
        )
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Empresa no encontrada."}

    def test_id_empresa_actual_propia_excluye_propios(
        self, client_a, empresa_a, metodo_generico
    ):
        pytest.importorskip("rapidfuzz")  # get_aplicado la usa cuando hay empresa actual
        MetodoPago.objects.create(
            nombre_metodo="Público Propio", tipo_metodo="OTRO",
            empresa=empresa_a, es_publico=True,
        )
        resp = client_a.get(
            URL_METODOS + "buscar_reutilizar/",
            {"id_empresa_actual": str(empresa_a.id_empresa)},
        )
        assert resp.status_code == 200
        nombres = {m["nombre_metodo"] for m in self._results(resp)}
        assert "Efectivo Global" in nombres
        # Los métodos de la propia empresa se excluyen (ya los tiene).
        assert "Público Propio" not in nombres


# ── SEC-M2: MetodoPagoEmpresaActiva no acepta empresa del cliente ────────────

class TestActivacionEmpresaReadOnly:
    def test_post_con_empresa_ajena_queda_en_la_propia(
        self, client_a, empresa_a, empresa_b
    ):
        # Método sin empresa ni flags → la señal de sync no crea filas previas.
        metodo = MetodoPago.objects.create(nombre_metodo="Suelto P01", tipo_metodo="OTRO")
        resp = client_a.post(URL_ACTIVAS, {
            "empresa": str(empresa_b.id_empresa),  # se ignora (read-only)
            "metodo_pago": str(metodo.id_metodo_pago),
            "activa": True,
        })
        assert resp.status_code == 201, resp.content
        fila = MetodoPagoEmpresaActiva.objects.get(metodo_pago=metodo)
        assert fila.empresa == empresa_a
        assert not MetodoPagoEmpresaActiva.objects.filter(
            empresa=empresa_b, metodo_pago=metodo
        ).exists()

    def test_post_con_metodo_privado_ajeno_400(self, client_a, metodo_privado_b):
        resp = client_a.post(URL_ACTIVAS, {
            "metodo_pago": str(metodo_privado_b.id_metodo_pago),
            "activa": True,
        })
        assert resp.status_code == 400
        assert resp.json() == {"metodo_pago": ["Método de pago no encontrado."]}
        assert not MetodoPagoEmpresaActiva.objects.filter(
            metodo_pago=metodo_privado_b
        ).exclude(empresa=metodo_privado_b.empresa).exists()

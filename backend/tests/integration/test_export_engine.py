"""
Tests del ExportEngine (export outbound origen → destino).

Verifican la orquestación: lectura del origen, escritura en el destino,
registro de JobSincronizacion (outbound), aislamiento multi-tenant y
persistencia del spreadsheet_id auto-creado. El origen/destino reales se
sustituyen por dobles para no depender de Odoo ni de Google.
"""

from unittest.mock import MagicMock

import pytest

from apps.integration_hub.connectors.base import ConnectorError, SyncResult
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
from apps.integration_hub.services import export_engine as export_engine_mod
from apps.integration_hub.services.export_engine import ExportEngine

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _proveedor(codigo, nombre):
    prov, _ = ConectorProveedor.objects.get_or_create(
        codigo=codigo,
        defaults={
            "nombre": nombre,
            "estado": "activo",
            "activo": True,
            "capacidades": ["contactos", "productos"],
        },
    )
    return prov


def _instancias(empresa, source_config_extra=None):
    prov_odoo = _proveedor("odoo", "Odoo")
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    origen = ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov_odoo,
        nombre="Odoo Origen",
        configuracion={"host": "https://x.odoo.com", "user": "u", "api_key": "k"},
        entidades_activas=["contactos"],
    )
    destino = ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=prov_sheets,
        nombre="Sheets Destino",
        configuracion={
            "service_account": {"client_email": "svc@p.iam.gserviceaccount.com"},
            "source_instancia_id": str(origen.pk),
            **(source_config_extra or {}),
        },
        entidades_activas=["contactos"],
    )
    return origen, destino


def _fake_connectors(
    monkeypatch, *, pull_result, push_result, spreadsheet_id="SHEET123"
):
    """Sustituye registry.get_connector por dobles según el proveedor."""
    fake_origen = MagicMock()
    fake_origen.pull_contactos.return_value = pull_result
    fake_destino = MagicMock()
    fake_destino.supports.return_value = True
    fake_destino.push_entidades.return_value = push_result
    fake_destino.spreadsheet_id = spreadsheet_id

    def fake_get(instancia):
        if instancia.id_proveedor.codigo == "google_sheets":
            return fake_destino
        return fake_origen

    monkeypatch.setattr(export_engine_mod.registry, "get_connector", fake_get)
    return fake_origen, fake_destino


def test_exportar_crea_job_outbound_con_contadores(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    _fake_connectors(
        monkeypatch,
        pull_result=[
            {"id_externo": "1", "nombre": "A"},
            {"id_externo": "2", "nombre": "B"},
        ],
        push_result=SyncResult(tipo_entidad="contactos", total=2, creados=2),
    )

    jobs = ExportEngine().exportar(destino, tipos=["contactos"])

    assert len(jobs) == 1
    job = jobs[0]
    assert job.direccion == "outbound"
    assert job.estado == "completado"
    assert job.tipo_entidad == "contactos"
    assert job.creados == 2
    assert job.total_registros == 2


def test_exportar_persiste_spreadsheet_id_autocreado(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    _fake_connectors(
        monkeypatch,
        pull_result=[{"id_externo": "1", "nombre": "A"}],
        push_result=SyncResult(tipo_entidad="contactos", total=1, creados=1),
        spreadsheet_id="NUEVO_ID",
    )

    ExportEngine().exportar(destino, tipos=["contactos"])

    destino.refresh_from_db()
    assert destino.get_config().get("spreadsheet_id") == "NUEVO_ID"


def test_exportar_usa_entidades_activas_si_no_se_indican(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    _fake_connectors(
        monkeypatch,
        pull_result=[{"id_externo": "1", "nombre": "A"}],
        push_result=SyncResult(tipo_entidad="contactos", total=1, creados=1),
    )
    jobs = ExportEngine().exportar(destino)  # sin tipos → entidades_activas
    assert [j.tipo_entidad for j in jobs] == ["contactos"]


def test_exportar_falla_sin_source_instancia(monkeypatch, empresa_a):
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    destino = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_sheets,
        nombre="Sheets Sin Origen",
        configuracion={
            "service_account": {"client_email": "x@y.iam.gserviceaccount.com"}
        },
        entidades_activas=["contactos"],
    )
    # get_connector se usa para el destino; el origen falla antes de pull.
    fake_destino = MagicMock()
    monkeypatch.setattr(
        export_engine_mod.registry, "get_connector", lambda inst: fake_destino
    )
    with pytest.raises(ConnectorError, match="source_instancia_id"):
        ExportEngine().exportar(destino, tipos=["contactos"])


def test_exportar_rechaza_origen_de_otra_empresa(monkeypatch, empresa_a, empresa_b):
    # Origen en empresa_b, destino en empresa_a → debe rechazarse (R-CODE-1).
    prov_odoo = _proveedor("odoo", "Odoo")
    prov_sheets = _proveedor("google_sheets", "Google Sheets")
    origen_b = ConectorInstancia.objects.create(
        id_empresa=empresa_b,
        id_proveedor=prov_odoo,
        nombre="Odoo Otra Empresa",
        configuracion={"host": "h", "user": "u", "api_key": "k"},
    )
    destino_a = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_sheets,
        nombre="Sheets A",
        configuracion={
            "service_account": {"client_email": "x@y.iam.gserviceaccount.com"},
            "source_instancia_id": str(origen_b.pk),
        },
        entidades_activas=["contactos"],
    )
    monkeypatch.setattr(
        export_engine_mod.registry, "get_connector", lambda inst: MagicMock()
    )
    with pytest.raises(ConnectorError, match="otra empresa"):
        ExportEngine().exportar(destino_a, tipos=["contactos"])


def test_exportar_pasa_limite_al_pull_del_origen(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    fake_origen, _ = _fake_connectors(
        monkeypatch,
        pull_result=[{"id_externo": "1", "nombre": "A"}],
        push_result=SyncResult(tipo_entidad="contactos", total=1, creados=1),
    )
    ExportEngine().exportar(destino, tipos=["contactos"])
    _, kwargs = fake_origen.pull_contactos.call_args
    assert kwargs["limite"] == ExportEngine.LIMITE_EXPORT


def test_exportar_marca_posible_truncamiento_si_alcanza_limite(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a, source_config_extra={"limite_export": 2})
    registros = [
        {"id_externo": "1", "nombre": "A"},
        {"id_externo": "2", "nombre": "B"},
    ]
    _fake_connectors(
        monkeypatch,
        pull_result=registros,
        push_result=SyncResult(tipo_entidad="contactos", total=2, creados=2),
    )

    jobs = ExportEngine().exportar(destino, tipos=["contactos"])

    # len(registros) == limite → aviso visible: el operador debe re-ejecutar.
    assert jobs[0].estado == "completado_con_errores"
    assert "limite_export" in jobs[0].resumen_errores[0]["error"]


def test_exportar_persiste_contactos_en_omni(monkeypatch, empresa_a):
    """Omni como hub: exportar Odoo→Sheets también deja los contactos en Omni."""
    from apps.core.models import Contacto

    origen, destino = _instancias(empresa_a)
    _fake_connectors(
        monkeypatch,
        pull_result=[
            {
                "id_externo": "1",
                "nombre": "Cliente A",
                "identificador_fiscal": "J-12345678-9",
                "email": "a@cliente.com",
                "es_cliente": True,
                "_checksum": "chk1",
            }
        ],
        push_result=SyncResult(tipo_entidad="contactos", total=1, creados=1),
    )

    jobs = ExportEngine().exportar(destino, tipos=["contactos"])

    # La data quedó almacenada en Omni con su estructura canónica.
    assert Contacto.objects.filter(id_empresa=empresa_a, rif="J-12345678-9").exists()
    # Y el resumen de persistencia queda en el job para trazabilidad.
    persist = jobs[0].parametros.get("omni_persistencia")
    assert persist is not None
    assert persist["creados"] == 1


def test_exportar_persistir_en_omni_desactivable(monkeypatch, empresa_a):
    """Con persistir_en_omni=False, exporta a Sheets pero NO guarda en Omni."""
    from apps.core.models import Contacto

    origen, destino = _instancias(
        empresa_a, source_config_extra={"persistir_en_omni": False}
    )
    _fake_connectors(
        monkeypatch,
        pull_result=[
            {
                "id_externo": "1",
                "nombre": "Cliente A",
                "identificador_fiscal": "J-99999999-9",
                "_checksum": "chk1",
            }
        ],
        push_result=SyncResult(tipo_entidad="contactos", total=1, creados=1),
    )

    jobs = ExportEngine().exportar(destino, tipos=["contactos"])

    assert not Contacto.objects.filter(id_empresa=empresa_a, rif="J-99999999-9").exists()
    assert "omni_persistencia" not in (jobs[0].parametros or {})
    assert jobs[0].estado == "completado"


def test_persistencia_fallida_no_rompe_la_exportacion(monkeypatch, empresa_a):
    """Si la persistencia en Omni revienta, la exportación a Sheets continúa."""
    origen, destino = _instancias(empresa_a)
    _, fake_destino = _fake_connectors(
        monkeypatch,
        pull_result=[{"id_externo": "1", "nombre": "A", "_checksum": "c"}],
        push_result=SyncResult(tipo_entidad="contactos", total=1, creados=1),
    )
    monkeypatch.setattr(
        "apps.integration_hub.services.sync_engine.SyncEngine.ingerir_en_omni",
        MagicMock(side_effect=RuntimeError("boom")),
    )

    jobs = ExportEngine().exportar(destino, tipos=["contactos"])

    # La exportación se completó pese al fallo de persistencia (best-effort).
    fake_destino.push_entidades.assert_called_once()
    assert jobs[0].estado == "completado"
    assert "error" in jobs[0].parametros["omni_persistencia"]


def test_ingerir_en_omni_crea_y_luego_omite_por_checksum(empresa_a):
    """ingerir_en_omni: crea la 1ª vez y omite si el checksum no cambió."""
    from apps.integration_hub.services.sync_engine import SyncEngine

    origen, _ = _instancias(empresa_a)
    eng = SyncEngine()
    regs = [
        {
            "id_externo": "1",
            "nombre": "Cliente A",
            "identificador_fiscal": "J-1",
            "_checksum": "c1",
        }
    ]

    r1 = eng.ingerir_en_omni(origen, "contactos", regs)
    assert r1["creados"] == 1

    r2 = eng.ingerir_en_omni(origen, "contactos", regs)
    assert r2["omitidos"] == 1
    assert r2["creados"] == 0


def test_ingerir_en_omni_omite_si_upsert_devuelve_none(monkeypatch, empresa_a):
    """Si _upsert_en_omni devuelve None (registro inválido), se omite."""
    from apps.integration_hub.services.sync_engine import SyncEngine

    origen, _ = _instancias(empresa_a)
    monkeypatch.setattr(SyncEngine, "_upsert_en_omni", lambda self, t, d, i: None)

    r = SyncEngine().ingerir_en_omni(
        origen, "contactos", [{"id_externo": "1", "_checksum": "c"}]
    )
    assert r["omitidos"] == 1
    assert r["creados"] == 0


def test_ingerir_en_omni_captura_error_por_registro(monkeypatch, empresa_a):
    """Un error en un registro no aborta el lote: se cuenta y se registra."""
    from apps.integration_hub.services.sync_engine import SyncEngine

    origen, _ = _instancias(empresa_a)
    monkeypatch.setattr(
        SyncEngine,
        "_upsert_en_omni",
        MagicMock(side_effect=RuntimeError("x")),
    )

    r = SyncEngine().ingerir_en_omni(
        origen, "contactos", [{"id_externo": "9", "_checksum": "c"}]
    )
    assert r["fallidos"] == 1
    assert r["errores"][0]["id_externo"] == "9"


def test_exportar_marca_job_fallido_si_pull_revienta(monkeypatch, empresa_a):
    origen, destino = _instancias(empresa_a)
    fake_origen, fake_destino = _fake_connectors(
        monkeypatch,
        pull_result=[],
        push_result=SyncResult(tipo_entidad="contactos"),
    )
    fake_origen.pull_contactos.side_effect = RuntimeError("Odoo caído")

    jobs = ExportEngine().exportar(destino, tipos=["contactos"])

    assert jobs[0].estado == "fallido"
    assert "Odoo caído" in jobs[0].resumen_errores[0]["error"]
    fake_destino.push_entidades.assert_not_called()

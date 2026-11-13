"""Reglas de integridad de Omni Connect y del CRM ligero (S1).

Cubre validadores, restricciones de BD (CheckConstraint / UniqueConstraint) y
la validación cross-tenant de FKs en ``clean()`` (R-CODE-1).
"""

import pytest

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.connect.models import Perfil, Tarjeta
from apps.connect.validators import (
    normalizar_slug,
    normalizar_uid_chip,
    validar_botones,
    validar_slug_perfil,
    validar_uid_chip,
)
from apps.crm.models import Etapa, Lead, Pipeline

from .builders import (
    consentimiento,
    crear_contacto,
    crear_etapa,
    crear_lead,
    crear_perfil,
    crear_pipeline,
    crear_tarjeta,
    crear_toque,
    crear_usuario,
)

# ── Validadores (sin BD) ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("slug", ["marco", "marco-romero", "ab1", "a" * 60, "ventas-2026"])
def test_slug_valido(slug):
    validar_slug_perfil(slug)


@pytest.mark.unit
@pytest.mark.parametrize(
    "slug",
    ["", "ab", "-marco", "marco-", "Marco", "marco romero", "marco_romero", "ma--rco", "a" * 61, "admin", "api"],
)
def test_slug_invalido(slug):
    with pytest.raises(ValidationError):
        validar_slug_perfil(slug)


@pytest.mark.unit
def test_uid_se_normaliza_y_valida():
    assert normalizar_uid_chip("04:a2:b3:c4:d5:e6:f7") == "04A2B3C4D5E6F7"
    assert normalizar_uid_chip(" 04-a2 b3c4 ") == "04A2B3C4"
    validar_uid_chip("04A2B3C4D5E6F7")


@pytest.mark.unit
@pytest.mark.parametrize("uid", ["", "04A2", "ZZZZZZZZ", "04A2B3C4D5E6F7A1B2C3D", "04A2B3C"])
def test_uid_invalido(uid):
    with pytest.raises(ValidationError):
        validar_uid_chip(uid)


@pytest.mark.unit
def test_normalizar_slug():
    assert normalizar_slug("  Juan-Perez ") == "juan-perez"
    assert normalizar_slug(None) == ""


_BOTON_OK = {"tipo": "web", "etiqueta": "Mi web", "valor": "https://ejemplo.com/x"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "botones",
    [
        [],
        [_BOTON_OK],
        [{"tipo": "whatsapp", "etiqueta": "WhatsApp", "valor": "+584121234567"}],
        [{"tipo": "telefono", "etiqueta": "Llamar", "valor": "02121234567"}],
        [{"tipo": "correo", "etiqueta": "Correo", "valor": "a@b.com"}],
        [{"tipo": "instagram", "etiqueta": "IG", "valor": "HTTP://instagram.com/u"}],
    ],
)
def test_botones_validos(botones):
    validar_botones(botones)


@pytest.mark.unit
@pytest.mark.parametrize(
    "botones",
    [
        {"tipo": "web"},  # no es lista
        "texto",
        [{"tipo": "web", "etiqueta": "x"}],  # faltan claves
        [{**_BOTON_OK, "extra": "1"}],  # clave extra
        [{**_BOTON_OK, "tipo": "script"}],  # tipo fuera del allowlist
        [{**_BOTON_OK, "valor": "javascript:alert(1)"}],  # esquema peligroso
        [{**_BOTON_OK, "valor": "data:text/html;base64,AAAA"}],
        [{**_BOTON_OK, "valor": "ftp://ejemplo.com"}],
        [{**_BOTON_OK, "valor": "https://a b.com"}],  # espacios
        [{**_BOTON_OK, "etiqueta": ""}],
        [{**_BOTON_OK, "etiqueta": "x" * 61}],
        [{**_BOTON_OK, "valor": 123}],  # no es texto
        [{"tipo": "whatsapp", "etiqueta": "W", "valor": "javascript:1"}],
        [{"tipo": "correo", "etiqueta": "C", "valor": "no-es-correo"}],
        [_BOTON_OK] * 31,  # demasiados botones
    ],
)
def test_botones_invalidos(botones):
    with pytest.raises(ValidationError):
        validar_botones(botones)


# ── Perfil ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_normaliza_slug_al_guardar_y_en_full_clean(empresa_a):
    perfil = crear_perfil(empresa_a, slug="  Juan-Perez ")
    perfil.refresh_from_db()
    assert perfil.slug == "juan-perez"

    otro = crear_perfil(empresa_a)
    otro.slug = "Ana-Lopez "  # lo que llega de un formulario/admin
    otro.full_clean()  # los validadores corren sobre el slug ya normalizado
    assert otro.slug == "ana-lopez"


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_slug_reservado_se_rechaza_en_bd_aun_sin_validadores(empresa_a):
    """CheckConstraint: protege rutas como /admin aunque se use objects.create/update."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Perfil.objects.bulk_create(
            [Perfil(id_empresa=empresa_a, usuario=crear_usuario(empresa_a), slug="admin", nombre_publico="X")]
        )


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_slug_en_mayusculas_se_rechaza_en_bd_con_update(empresa_a):
    perfil = crear_perfil(empresa_a)
    with pytest.raises(IntegrityError), transaction.atomic():
        Perfil.objects.filter(pk=perfil.pk).update(slug="MAYUS-CULAS")


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_valida_botones_en_full_clean(empresa_a):
    perfil = crear_perfil(empresa_a)
    perfil.botones = [{"tipo": "web", "etiqueta": "Web", "valor": "javascript:alert(1)"}]
    with pytest.raises(ValidationError) as exc:
        perfil.full_clean()
    assert "botones" in exc.value.message_dict


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_un_solo_perfil_por_usuario(empresa_a):
    perfil = crear_perfil(empresa_a)
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_perfil(empresa_a, usuario=perfil.usuario)


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_slug_es_unico_entre_empresas(empresa_a, empresa_b):
    """La URL pública no lleva tenant: un slug no puede repetirse en otra empresa."""
    crear_perfil(empresa_a, slug="marco-romero")
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_perfil(empresa_b, slug="marco-romero")


@pytest.mark.django_db
@pytest.mark.integration
def test_perfil_rechaza_usuario_de_otra_empresa(empresa_a, empresa_b):
    perfil = crear_perfil(empresa_a)
    perfil.usuario = crear_usuario(empresa_b)
    with pytest.raises(ValidationError) as exc:
        perfil.full_clean()
    assert "usuario" in exc.value.message_dict


# ── Tarjeta ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_guarda_uid_normalizado(empresa_a):
    tarjeta = crear_tarjeta(empresa_a, uid_chip="04:a2:b3:c4:d5:e6:f7")
    tarjeta.refresh_from_db()
    assert tarjeta.uid_chip == "04A2B3C4D5E6F7"
    assert tarjeta.estado == Tarjeta.Estado.INVENTARIO
    assert tarjeta.perfil is None  # tarjeta en inventario, aún sin asignar


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_full_clean_acepta_uid_con_separadores_y_minusculas(empresa_a):
    """El validador de campo corre antes de clean(): debe ver el UID ya normalizado."""
    tarjeta = crear_tarjeta(empresa_a)
    tarjeta.uid_chip = "04:a2:b3:c4:d5:e6:f7"
    tarjeta.full_clean()
    assert tarjeta.uid_chip == "04A2B3C4D5E6F7"


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_activa_registra_fecha_de_activacion(empresa_a):
    perfil = crear_perfil(empresa_a)
    inventario = crear_tarjeta(empresa_a)
    assert inventario.fecha_activacion is None

    activa = crear_tarjeta(empresa_a, perfil=perfil, estado=Tarjeta.Estado.ACTIVA)
    assert activa.fecha_activacion is not None


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_uid_es_unico_entre_empresas(empresa_a, empresa_b):
    """El chip es físico: dos tenants no pueden registrar el mismo UID."""
    crear_tarjeta(empresa_a, uid_chip="04A2B3C4D5E6F7")
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_tarjeta(empresa_b, uid_chip="04:a2:b3:c4:d5:e6:f7")


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_activa_exige_perfil(empresa_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_tarjeta(empresa_a, perfil=None, estado=Tarjeta.Estado.ACTIVA)


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_activa_con_perfil_ok_y_reasignable(empresa_a):
    perfil1, perfil2 = crear_perfil(empresa_a), crear_perfil(empresa_a)
    tarjeta = crear_tarjeta(empresa_a, perfil=perfil1, estado=Tarjeta.Estado.ACTIVA)
    tarjeta.perfil = perfil2
    tarjeta.save()
    tarjeta.refresh_from_db()
    assert tarjeta.perfil_id == perfil2.pk


@pytest.mark.django_db
@pytest.mark.integration
def test_tarjeta_rechaza_perfil_de_otra_empresa(empresa_a, empresa_b):
    tarjeta = crear_tarjeta(empresa_a)
    tarjeta.perfil = crear_perfil(empresa_b)
    with pytest.raises(ValidationError) as exc:
        tarjeta.full_clean()
    assert "perfil" in exc.value.message_dict


# ── Toque ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
def test_toque_sin_tarjeta_es_valido_para_qr_o_enlace(empresa_a):
    toque = crear_toque(empresa_a, origen="QR")
    toque.full_clean()
    assert toque.tarjeta is None and toque.fecha_toque is not None


@pytest.mark.django_db
@pytest.mark.integration
def test_toque_rechaza_perfil_o_tarjeta_de_otra_empresa(empresa_a, empresa_b):
    toque = crear_toque(empresa_a)
    toque.perfil = crear_perfil(empresa_b)
    toque.tarjeta = crear_tarjeta(empresa_b)
    with pytest.raises(ValidationError) as exc:
        toque.full_clean()
    assert {"perfil", "tarjeta"} <= set(exc.value.message_dict)


@pytest.mark.django_db
@pytest.mark.integration
def test_toque_rechaza_tarjeta_de_otro_perfil_o_sin_perfil(empresa_a):
    perfil_a, perfil_b = crear_perfil(empresa_a), crear_perfil(empresa_a)
    tarjeta_de_b = crear_tarjeta(empresa_a, perfil=perfil_b, estado=Tarjeta.Estado.ACTIVA)
    tarjeta_inventario = crear_tarjeta(empresa_a)

    for tarjeta in (tarjeta_de_b, tarjeta_inventario):
        toque = crear_toque(empresa_a, perfil=perfil_a)
        toque.tarjeta = tarjeta
        with pytest.raises(ValidationError) as exc:
            toque.full_clean()
        assert "tarjeta" in exc.value.message_dict

    # Coherente: la tarjeta pertenece al perfil del toque.
    toque = crear_toque(empresa_a, perfil=perfil_b, tarjeta=tarjeta_de_b)
    toque.full_clean()


@pytest.mark.django_db
@pytest.mark.integration
def test_no_se_puede_borrar_perfil_con_toques(empresa_a):
    """PROTECT: la analítica histórica no se pierde por borrar el perfil."""
    from django.db.models import ProtectedError

    toque = crear_toque(empresa_a)
    with pytest.raises(ProtectedError):
        toque.perfil.delete()


# ── Pipeline y Etapa ──────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
def test_un_solo_pipeline_predeterminado_por_empresa(empresa_a, empresa_b):
    crear_pipeline(empresa_a, es_predeterminado=True)
    crear_pipeline(empresa_b, es_predeterminado=True)  # otra empresa: permitido
    crear_pipeline(empresa_a, es_predeterminado=False)  # no predeterminado: permitido
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_pipeline(empresa_a, es_predeterminado=True)


@pytest.mark.django_db
@pytest.mark.integration
def test_pipeline_desactivado_libera_nombre_y_predeterminado(empresa_a):
    viejo = crear_pipeline(empresa_a, nombre="Ventas", es_predeterminado=True)
    viejo.soft_delete()
    # Con el viejo desactivado se puede reutilizar el nombre y fijar otro predeterminado.
    crear_pipeline(empresa_a, nombre="Ventas", es_predeterminado=True)
    assert Pipeline.objects.filter(id_empresa=empresa_a, nombre="Ventas").count() == 2


@pytest.mark.django_db
@pytest.mark.integration
def test_etapa_nombre_unico_entre_activas_pero_orden_repetible(empresa_a):
    pipeline = crear_pipeline(empresa_a)
    nuevo = crear_etapa(empresa_a, pipeline, nombre="Nuevo", orden=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_etapa(empresa_a, pipeline, nombre="Nuevo", orden=2)
    # El orden NO es único: reordenar intercambia posiciones sin chocar.
    otra = crear_etapa(empresa_a, pipeline, nombre="Contactado", orden=2)
    Etapa.objects.filter(pk=nuevo.pk).update(orden=2)
    Etapa.objects.filter(pk=otra.pk).update(orden=1)
    assert list(pipeline.etapas.values_list("nombre", flat=True)) == ["Contactado", "Nuevo"]
    # Mismo nombre en otro pipeline: permitido. Y tras desactivar, el nombre se libera.
    crear_etapa(empresa_a, crear_pipeline(empresa_a), nombre="Nuevo", orden=1)
    nuevo.soft_delete()
    crear_etapa(empresa_a, pipeline, nombre="Nuevo", orden=3)


@pytest.mark.django_db
@pytest.mark.integration
def test_etapa_rechaza_pipeline_de_otra_empresa(empresa_a, empresa_b):
    etapa = crear_etapa(empresa_a)
    etapa.pipeline = crear_pipeline(empresa_b)
    with pytest.raises(ValidationError) as exc:
        etapa.full_clean()
    assert "pipeline" in exc.value.message_dict


# ── Lead ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
def test_lead_manual_no_exige_consentimiento(empresa_a):
    lead = crear_lead(empresa_a, fuente=Lead.Fuente.MANUAL)
    lead.full_clean()
    assert lead.consentimiento_aceptado is False


@pytest.mark.django_db
@pytest.mark.integration
@pytest.mark.parametrize("fuente", [Lead.Fuente.NFC, Lead.Fuente.QR, Lead.Fuente.ENLACE])
def test_lead_publico_exige_consentimiento(empresa_a, fuente):
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_lead(empresa_a, fuente=fuente)


@pytest.mark.django_db
@pytest.mark.integration
def test_lead_publico_con_consentimiento_completo_ok(empresa_a):
    lead = crear_lead(empresa_a, fuente=Lead.Fuente.NFC, **consentimiento())
    lead.refresh_from_db()
    assert lead.consentimiento_aceptado and lead.consentimiento_fecha is not None


@pytest.mark.django_db
@pytest.mark.integration
@pytest.mark.parametrize(
    "faltante", [{"consentimiento_fecha": None}, {"consentimiento_texto": ""}]
)
def test_consentimiento_aceptado_exige_fecha_y_texto(empresa_a, faltante):
    with pytest.raises(IntegrityError), transaction.atomic():
        crear_lead(empresa_a, fuente=Lead.Fuente.MANUAL, **consentimiento(**faltante))


@pytest.mark.django_db
@pytest.mark.integration
def test_lead_rechaza_fks_de_otra_empresa(empresa_a, empresa_b):
    lead = crear_lead(empresa_a)
    lead.pipeline = crear_pipeline(empresa_b)
    lead.etapa = crear_etapa(empresa_b, lead.pipeline)
    lead.perfil = crear_perfil(empresa_b)
    lead.tarjeta = crear_tarjeta(empresa_b)
    lead.contacto = crear_contacto(empresa_b)
    with pytest.raises(ValidationError) as exc:
        lead.full_clean()
    assert {"pipeline", "etapa", "perfil", "tarjeta", "contacto"} <= set(exc.value.message_dict)


@pytest.mark.django_db
@pytest.mark.integration
def test_lead_rechaza_etapa_de_otro_pipeline(empresa_a):
    lead = crear_lead(empresa_a)
    lead.etapa = crear_etapa(empresa_a, crear_pipeline(empresa_a))
    with pytest.raises(ValidationError) as exc:
        lead.full_clean()
    assert "etapa" in exc.value.message_dict


@pytest.mark.django_db
@pytest.mark.integration
def test_lead_rechaza_tarjeta_que_no_es_del_perfil(empresa_a):
    perfil_a, perfil_b = crear_perfil(empresa_a), crear_perfil(empresa_a)
    tarjeta_de_b = crear_tarjeta(empresa_a, perfil=perfil_b, estado=Tarjeta.Estado.ACTIVA)
    lead = crear_lead(empresa_a, fuente=Lead.Fuente.NFC, perfil=perfil_a, **consentimiento())
    lead.tarjeta = tarjeta_de_b
    with pytest.raises(ValidationError) as exc:
        lead.full_clean()
    assert "tarjeta" in exc.value.message_dict


@pytest.mark.django_db
@pytest.mark.integration
def test_lead_rechaza_propietario_de_otra_empresa(empresa_a, empresa_b):
    lead = crear_lead(empresa_a)
    lead.propietario = crear_usuario(empresa_b)
    with pytest.raises(ValidationError) as exc:
        lead.full_clean()
    assert "propietario" in exc.value.message_dict


@pytest.mark.django_db
@pytest.mark.integration
def test_borrar_tarjeta_no_borra_leads_capturados(empresa_a):
    """SET_NULL: el lead sobrevive aunque se elimine la tarjeta que lo capturó."""
    perfil = crear_perfil(empresa_a)
    tarjeta = crear_tarjeta(empresa_a, perfil=perfil, estado=Tarjeta.Estado.ACTIVA)
    lead = crear_lead(empresa_a, fuente=Lead.Fuente.NFC, tarjeta=tarjeta, perfil=perfil, **consentimiento())
    tarjeta.hard_delete() if hasattr(tarjeta, "hard_delete") else tarjeta.delete()
    lead.refresh_from_db()
    assert lead.tarjeta is None and lead.perfil_id == perfil.pk

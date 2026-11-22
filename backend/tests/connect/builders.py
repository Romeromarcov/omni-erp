"""Builders de datos para los tests de Omni Connect / CRM ligero (S1).

Cada builder recibe la empresa explícitamente (R-CODE-1) y crea lo mínimo
necesario para que el registro sea válido; los slugs y UIDs son únicos por
secuencia porque son únicos globalmente.
"""

import itertools

from tests.factories import UsuariosFactory

from django.utils import timezone

from apps.connect.models import Perfil, Tarjeta, Toque
from apps.core.models import Contacto
from apps.crm.models import Etapa, Lead, Pipeline

_seq = itertools.count(1)


def crear_usuario(empresa):
    n = next(_seq)
    return UsuariosFactory(username=f"connect_user_{n}", email=f"connect{n}@test.local", empresa=empresa)


def crear_perfil(empresa, usuario=None, **extra):
    n = next(_seq)
    usuario = usuario or crear_usuario(empresa)
    datos = {
        "id_empresa": empresa,
        "usuario": usuario,
        "slug": f"perfil-{n:04d}",
        "nombre_publico": f"Perfil {n}",
    }
    datos.update(extra)
    return Perfil.objects.create(**datos)


def crear_tarjeta(empresa, perfil=None, **extra):
    n = next(_seq)
    datos = {"id_empresa": empresa, "perfil": perfil, "uid_chip": f"04A2{n:010X}"}
    datos.update(extra)
    return Tarjeta.objects.create(**datos)


def crear_toque(empresa, perfil=None, tarjeta=None, **extra):
    perfil = perfil or crear_perfil(empresa)
    datos = {"id_empresa": empresa, "perfil": perfil, "tarjeta": tarjeta}
    datos.update(extra)
    return Toque.objects.create(**datos)


def crear_pipeline(empresa, **extra):
    n = next(_seq)
    datos = {"id_empresa": empresa, "nombre": f"Pipeline {n}"}
    datos.update(extra)
    return Pipeline.objects.create(**datos)


def crear_etapa(empresa, pipeline=None, **extra):
    pipeline = pipeline or crear_pipeline(empresa)
    n = next(_seq)
    datos = {"id_empresa": empresa, "pipeline": pipeline, "nombre": f"Etapa {n}", "orden": n}
    datos.update(extra)
    return Etapa.objects.create(**datos)


def crear_contacto(empresa, **extra):
    n = next(_seq)
    datos = {"id_empresa": empresa, "nombre": f"Contacto {n}"}
    datos.update(extra)
    return Contacto.objects.create(**datos)


def crear_lead(empresa, pipeline=None, etapa=None, propietario=None, **extra):
    """Lead MANUAL válido (sin consentimiento obligatorio) salvo que se indique otra fuente."""
    if etapa is None:
        pipeline = pipeline or crear_pipeline(empresa)
        etapa = crear_etapa(empresa, pipeline)
    pipeline = pipeline or etapa.pipeline
    propietario = propietario or crear_usuario(empresa)
    n = next(_seq)
    datos = {
        "id_empresa": empresa,
        "nombre": f"Lead {n}",
        "pipeline": pipeline,
        "etapa": etapa,
        "propietario": propietario,
    }
    datos.update(extra)
    return Lead.objects.create(**datos)


def consentimiento(**extra):
    """Campos de consentimiento aceptado, completos y consistentes."""
    datos = {
        "consentimiento_aceptado": True,
        "consentimiento_fecha": timezone.now(),
        "consentimiento_texto": "Acepto que se guarden mis datos para ser contactado.",
    }
    datos.update(extra)
    return datos

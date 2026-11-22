"""Eval suite — Agentes IA Omni Connect (Plan 07 S12).

Ejecuta los casos dorados de ``connect_calificador`` y ``connect_seguimiento``
sin base de datos (idéntico al job CI ``Agent Eval``) y verifica:
  - Precisión global >= 80 % en clasificación de prioridad (``connect_calificador``).
  - Precisión global >= 80 % en acción + canal (``connect_seguimiento``).
  - Invariante de cumplimiento: leads anonimizados, inactivos, cerrados o sin
    consentimiento siempre producen ``NO_CONTACTAR`` / ``NINGUNO``.
  - Toda propuesta ``ENVIO_EXTERNO`` marca ``requiere_aprobacion=True`` con
    ``codigo_tipo_aprobacion="CONNECT_ENVIO_EXTERNO"``.
"""

from __future__ import annotations

import pytest

from apps.agentes.connect_agents import (
    CODIGO_APROBACION_ENVIO_EXTERNO,
    calificar_lead_deterministico,
    proponer_seguimiento_deterministico,
)

PRECISION_MINIMA_CONNECT = 0.80

CASOS_DORADOS_CALIFICADOR: list[dict] = [
    # ── Prioridad ALTA (score >= 70) ──────────────────────────────────────────
    {
        "id": "cal-alta-01",
        "datos": {
            "nombre": "Carlos",
            "apellido": "Mendoza",
            "empresa_nombre": "Distribuidora Los Andes C.A.",
            "cargo": "Gerente de Compras",
            "email": "cmendoza@losandes.com.ve",
            "telefono": "+584141234567",
            "mensaje": "Necesitamos cotización urgente para compra mensual de 500 unidades.",
            "fuente": "NFC",
            "dias_desde_captura": 0,
            "total_toques": 3,
            "tiene_contacto_previo": False,
        },
        "prioridad_esperada": "ALTA",
    },
    {
        "id": "cal-alta-02",
        "datos": {
            "nombre": "Elena",
            "empresa_nombre": "Grupo Industrial Orinoco",
            "cargo": "Directora de Operaciones",
            "email": "elena@orinocoind.com",
            "telefono": "+584122223344",
            "mensaje": "Queremos agendar demo y revisar presupuesto corporativo.",
            "fuente": "NFC",
            "dias_desde_captura": 1,
            "total_toques": 2,
        },
        "prioridad_esperada": "ALTA",
    },
    {
        "id": "cal-alta-03",
        "datos": {
            "nombre": "Roberto",
            "empresa_nombre": "AutoPartes Centro",
            "cargo": "Socio",
            "email": "roberto@autopartescentro.com",
            "telefono": "+584245556677",
            "mensaje": "Somos distribuidor mayorista, enviar lista de precios y contrato.",
            "fuente": "QR",
            "dias_desde_captura": 2,
            "total_toques": 1,
        },
        "prioridad_esperada": "ALTA",
    },
    {
        "id": "cal-alta-04",
        "datos": {
            "nombre": "Patricia",
            "empresa_nombre": "Flota Express Caracas",
            "cargo": "Jefe de Flota",
            "email": "patricia@flotaexpress.ve",
            "telefono": "+584161112233",
            "mensaje": "Requerimos orden de compra para flota de 40 vehículos esta semana.",
            "fuente": "ENLACE",
            "dias_desde_captura": 1,
            "total_toques": 2,
            "tiene_contacto_previo": True,
        },
        "prioridad_esperada": "ALTA",
    },
    {
        "id": "cal-alta-05",
        "datos": {
            "nombre": "Andrés",
            "empresa_nombre": "Ferretería Bolívar",
            "cargo": "Dueño",
            "email": "andres@ferrebolivar.com",
            "telefono": "+584148889900",
            "mensaje": "Listo para comprar primer pedido al mayor con factura fiscal.",
            "fuente": "NFC",
            "dias_desde_captura": 0,
            "total_toques": 1,
        },
        "prioridad_esperada": "ALTA",
    },
    {
        "id": "cal-alta-06",
        "datos": {
            "nombre": "Mariana",
            "empresa_nombre": "Comercializadora Zulia",
            "cargo": "CEO",
            "email": "mariana@comzulia.com",
            "telefono": "+584129998877",
            "mensaje": "Solicito reunión comercial para cotizar volumen mensual.",
            "fuente": "QR",
            "dias_desde_captura": 3,
            "total_toques": 2,
            "total_actividades": 1,
        },
        "prioridad_esperada": "ALTA",
    },
    # ── Prioridad MEDIA (40 <= score < 70) ────────────────────────────────────
    {
        "id": "cal-media-01",
        "datos": {
            "nombre": "Luis",
            "empresa_nombre": "Taller El Ávila",
            "email": "luis.avila@gmail.com",
            "telefono": "+584143334455",
            "mensaje": "Hola, quisiera información general de sus productos.",
            "fuente": "QR",
            "dias_desde_captura": 4,
            "total_toques": 1,
        },
        "prioridad_esperada": "MEDIA",
    },
    {
        "id": "cal-media-02",
        "datos": {
            "nombre": "Sofía",
            "empresa_nombre": "",
            "email": "sofia.perez@outlook.com",
            "telefono": "+584127778899",
            "mensaje": "Estoy interesada en conocer disponibilidad y catálogo.",
            "fuente": "NFC",
            "dias_desde_captura": 5,
            "total_toques": 1,
        },
        "prioridad_esperada": "MEDIA",
    },
    {
        "id": "cal-media-03",
        "datos": {
            "nombre": "Diego",
            "empresa_nombre": "Servicios Delta",
            "email": "diego@serviciosdelta.com",
            "telefono": "",
            "mensaje": "Consulta sobre servicios para oficinas.",
            "fuente": "ENLACE",
            "dias_desde_captura": 6,
            "total_toques": 1,
        },
        "prioridad_esperada": "MEDIA",
    },
    {
        "id": "cal-media-04",
        "datos": {
            "nombre": "Valeria",
            "empresa_nombre": "Inversiones Sol",
            "email": "",
            "telefono": "+584241112200",
            "mensaje": "Nos vimos en la feria, envíame el catálogo cuando puedas.",
            "fuente": "NFC",
            "dias_desde_captura": 3,
            "total_toques": 1,
        },
        "prioridad_esperada": "MEDIA",
    },
    {
        "id": "cal-media-05",
        "datos": {
            "nombre": "Jorge",
            "empresa_nombre": "Bodegón Este",
            "email": "jorgebodegon@gmail.com",
            "telefono": "+584162223311",
            "mensaje": "",
            "fuente": "MANUAL",
            "dias_desde_captura": 2,
            "total_toques": 0,
        },
        "prioridad_esperada": "MEDIA",
    },
    {
        "id": "cal-media-06",
        "datos": {
            "nombre": "Gabriela",
            "empresa_nombre": "",
            "email": "gabi@empresa-local.com",
            "telefono": "",
            "mensaje": "Me interesa cotizar un servicio pequeño más adelante.",
            "fuente": "QR",
            "dias_desde_captura": 10,
            "total_toques": 1,
        },
        "prioridad_esperada": "MEDIA",
    },
    # ── Prioridad BAJA (score < 40) ───────────────────────────────────────────
    {
        "id": "cal-baja-01",
        "datos": {
            "nombre": "Pedro",
            "empresa_nombre": "",
            "email": "pedro123@gmail.com",
            "telefono": "",
            "mensaje": "Envío mi curriculum para vacante de empleo.",
            "fuente": "ENLACE",
            "dias_desde_captura": 1,
            "total_toques": 1,
        },
        "prioridad_esperada": "BAJA",
    },
    {
        "id": "cal-baja-02",
        "datos": {
            "nombre": "Test User",
            "empresa_nombre": "",
            "email": "qa@gmail.com",
            "telefono": "+584140000001",
            "mensaje": "Esto es una prueba interna del formulario.",
            "fuente": "QR",
            "dias_desde_captura": 0,
            "total_toques": 1,
        },
        "prioridad_esperada": "BAJA",
    },
    {
        "id": "cal-baja-03",
        "datos": {
            "nombre": "Visitante",
            "empresa_nombre": "",
            "email": "",
            "telefono": "",
            "mensaje": "Hola",
            "fuente": "ENLACE",
            "dias_desde_captura": 15,
            "total_toques": 0,
        },
        "prioridad_esperada": "BAJA",
    },
    {
        "id": "cal-baja-04",
        "datos": {
            "nombre": "Antiguo",
            "empresa_nombre": "",
            "email": "antiguo@hotmail.com",
            "telefono": "",
            "mensaje": "",
            "fuente": "IMPORTACION",
            "dias_desde_captura": 60,
            "total_toques": 0,
        },
        "prioridad_esperada": "BAJA",
    },
    {
        "id": "cal-baja-05",
        "datos": {
            "nombre": "Curioso",
            "empresa_nombre": "",
            "email": "curioso@yahoo.com",
            "telefono": "",
            "mensaje": "Solo mirando, no gracias por ahora.",
            "fuente": "NFC",
            "dias_desde_captura": 2,
            "total_toques": 1,
        },
        "prioridad_esperada": "BAJA",
    },
    {
        "id": "cal-baja-06",
        "datos": {
            "nombre": "Anonimizado",
            "empresa_nombre": "",
            "email": "",
            "telefono": "",
            "mensaje": "",
            "fuente": "NFC",
            "anonimizado": True,
            "activo": False,
        },
        "prioridad_esperada": "BAJA",
    },
]


CASOS_DORADOS_SEGUIMIENTO: list[dict] = [
    # ── Guardrails NO_CONTACTAR ───────────────────────────────────────────────
    {
        "id": "seg-nocontact-01-anonimizado",
        "datos": {
            "nombre": "Anonimizado",
            "email": "",
            "telefono": "",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": True,
            "activo": False,
        },
        "accion_esperada": "NO_CONTACTAR",
        "canal_esperado": "NINGUNO",
        "requiere_aprobacion": False,
    },
    {
        "id": "seg-nocontact-02-sin-consentimiento",
        "datos": {
            "nombre": "Manual Sin OptIn",
            "email": "manual@empresa.com",
            "telefono": "+584141112233",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": False,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "NO_CONTACTAR",
        "canal_esperado": "NINGUNO",
        "requiere_aprobacion": False,
    },
    {
        "id": "seg-nocontact-03-ganado",
        "datos": {
            "nombre": "Cliente Ganado",
            "email": "ganado@empresa.com",
            "telefono": "+584121112233",
            "etapa_tipo": "GANADA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "NO_CONTACTAR",
        "canal_esperado": "NINGUNO",
        "requiere_aprobacion": False,
    },
    {
        "id": "seg-nocontact-04-perdido",
        "datos": {
            "nombre": "Lead Perdido",
            "email": "perdido@empresa.com",
            "telefono": "+584241112233",
            "etapa_tipo": "PERDIDA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "NO_CONTACTAR",
        "canal_esperado": "NINGUNO",
        "requiere_aprobacion": False,
    },
    {
        "id": "seg-nocontact-05-inactivo",
        "datos": {
            "nombre": "Lead Inactivo",
            "email": "inactivo@empresa.com",
            "telefono": "+584161112233",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": False,
        },
        "accion_esperada": "NO_CONTACTAR",
        "canal_esperado": "NINGUNO",
        "requiere_aprobacion": False,
    },
    # ── TAREA_INTERNA (sin envío externo) ─────────────────────────────────────
    {
        "id": "seg-tarea-01-sin-canales",
        "datos": {
            "nombre": "Sin Contacto",
            "email": "",
            "telefono": "",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "TAREA_INTERNA",
        "canal_esperado": "NINGUNO",
        "requiere_aprobacion": False,
    },
    {
        "id": "seg-tarea-02-pide-llamada",
        "datos": {
            "nombre": "Fernando",
            "empresa_nombre": "Constructora Norte",
            "email": "fernando@cnorte.com",
            "telefono": "+584145554433",
            "mensaje": "Por favor llamar hoy en la tarde para revisar especificaciones.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "TAREA_INTERNA",
        "canal_esperado": "LLAMADA",
        "requiere_aprobacion": False,
    },
    {
        "id": "seg-tarea-03-alta-sin-respuesta",
        "datos": {
            "nombre": "Lucía",
            "empresa_nombre": "Alimentos Sur",
            "email": "lucia@alimentossur.com",
            "telefono": "+584126667788",
            "mensaje": "Interesada en distribución regional.",
            "prioridad": "ALTA",
            "dias_sin_contacto": 6,
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "TAREA_INTERNA",
        "canal_esperado": "LLAMADA",
        "requiere_aprobacion": False,
    },
    # ── ENVIO_EXTERNO EMAIL (requiere CONNECT_ENVIO_EXTERNO) ──────────────────
    {
        "id": "seg-email-01-cotizacion",
        "datos": {
            "nombre": "Ana",
            "empresa_nombre": "Lubricantes Lara",
            "email": "ana@lublara.com",
            "telefono": "+584141239876",
            "mensaje": "Por favor enviar cotización formal en PDF.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "EMAIL",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-email-02-solo-correo",
        "datos": {
            "nombre": "Miguel",
            "empresa_nombre": "Tech Solutions",
            "email": "miguel@techsolutions.io",
            "telefono": "",
            "mensaje": "Quisiera recibir más información.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "EMAIL",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-email-03-catalogo",
        "datos": {
            "nombre": "Carmen",
            "empresa_nombre": "FarmaExpress",
            "email": "carmen@farmaexpress.com",
            "telefono": "+584243214567",
            "mensaje": "Envíame el catálogo y lista de precios a mi correo.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "EMAIL",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-email-04-presupuesto",
        "datos": {
            "nombre": "Héctor",
            "empresa_nombre": "Logística Central",
            "email": "hector@logcentral.com",
            "telefono": "+584169876543",
            "mensaje": "Necesito presupuesto para 12 tambores.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "EMAIL",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-email-05-propuesta",
        "datos": {
            "nombre": "Daniela",
            "empresa_nombre": "Hotel Costa",
            "email": "compras@hotelcosta.com",
            "telefono": "",
            "mensaje": "Agradecemos propuesta comercial.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "EMAIL",
        "requiere_aprobacion": True,
    },
    # ── ENVIO_EXTERNO WHATSAPP (requiere CONNECT_ENVIO_EXTERNO) ───────────────
    {
        "id": "seg-wa-01-solo-telefono",
        "datos": {
            "nombre": "José",
            "empresa_nombre": "Repuestos Miranda",
            "email": "",
            "telefono": "+584142221100",
            "mensaje": "Me gustó la presentación en el stand.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "WHATSAPP",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-wa-02-nfc-contacto-rapido",
        "datos": {
            "nombre": "Raúl",
            "empresa_nombre": "AutoLavado Este",
            "email": "raul@autolavado.com",
            "telefono": "+584124445566",
            "mensaje": "Gusto en conocerte, seguimos en contacto por aquí.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "WHATSAPP",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-wa-03-whatsapp-disponibilidad",
        "datos": {
            "nombre": "Nadia",
            "empresa_nombre": "Taller Rápido",
            "email": "",
            "telefono": "+584248887766",
            "mensaje": "Avísame disponibilidad de aceite 15W40.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "WHATSAPP",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-wa-04-sin-mensaje",
        "datos": {
            "nombre": "Óscar",
            "empresa_nombre": "",
            "email": "oscar@gmail.com",
            "telefono": "+584163332211",
            "mensaje": "",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "WHATSAPP",
        "requiere_aprobacion": True,
    },
    {
        "id": "seg-wa-05-visita-tienda",
        "datos": {
            "nombre": "Isabel",
            "empresa_nombre": "Mercados Unidos",
            "email": "isabel@mercadosunidos.com",
            "telefono": "+584149990011",
            "mensaje": "Nos vemos la próxima semana en tienda.",
            "etapa_tipo": "ABIERTA",
            "consentimiento_aceptado": True,
            "anonimizado": False,
            "activo": True,
        },
        "accion_esperada": "ENVIO_EXTERNO",
        "canal_esperado": "WHATSAPP",
        "requiere_aprobacion": True,
    },
]


class TestEvalConnectCalificador:
    """Eval suite offline (sin BD) para ``connect_calificador``."""

    def test_tamanio_y_cobertura_dataset(self):
        assert len(CASOS_DORADOS_CALIFICADOR) >= 15
        prioridades = {caso["prioridad_esperada"] for caso in CASOS_DORADOS_CALIFICADOR}
        assert prioridades == {"ALTA", "MEDIA", "BAJA"}

    @pytest.mark.parametrize("caso", CASOS_DORADOS_CALIFICADOR, ids=[c["id"] for c in CASOS_DORADOS_CALIFICADOR])
    def test_caso_individual_calificador(self, caso):
        res = calificar_lead_deterministico(caso["datos"])
        assert res["prioridad"] == caso["prioridad_esperada"], (
            f"[{caso['id']}] esperada={caso['prioridad_esperada']}, obtenida={res['prioridad']} "
            f"(score={res['score']}, factores={res['factores']})"
        )
        assert 0 <= res["score"] <= 100
        assert 0.0 <= res["confianza"] <= 1.0
        assert res["razonamiento"]

    def test_precision_global_calificador(self):
        total = len(CASOS_DORADOS_CALIFICADOR)
        correctos = sum(
            1
            for caso in CASOS_DORADOS_CALIFICADOR
            if calificar_lead_deterministico(caso["datos"])["prioridad"] == caso["prioridad_esperada"]
        )
        precision = correctos / total
        assert (
            precision >= PRECISION_MINIMA_CONNECT
        ), f"Precisión connect_calificador: {precision:.1%} ({correctos}/{total}), mínimo {PRECISION_MINIMA_CONNECT:.0%}"


class TestEvalConnectSeguimiento:
    """Eval suite offline (sin BD) para ``connect_seguimiento``."""

    def test_tamanio_y_cobertura_dataset(self):
        assert len(CASOS_DORADOS_SEGUIMIENTO) >= 15
        acciones = {caso["accion_esperada"] for caso in CASOS_DORADOS_SEGUIMIENTO}
        canales = {caso["canal_esperado"] for caso in CASOS_DORADOS_SEGUIMIENTO}
        assert acciones == {"ENVIO_EXTERNO", "TAREA_INTERNA", "NO_CONTACTAR"}
        assert {"EMAIL", "WHATSAPP", "LLAMADA", "NINGUNO"}.issubset(canales)

    @pytest.mark.parametrize("caso", CASOS_DORADOS_SEGUIMIENTO, ids=[c["id"] for c in CASOS_DORADOS_SEGUIMIENTO])
    def test_caso_individual_seguimiento(self, caso):
        res = proponer_seguimiento_deterministico(caso["datos"])
        assert (
            res["accion"] == caso["accion_esperada"]
        ), f"[{caso['id']}] accion esperada={caso['accion_esperada']}, obtenida={res['accion']}"
        assert (
            res["canal"] == caso["canal_esperado"]
        ), f"[{caso['id']}] canal esperado={caso['canal_esperado']}, obtenido={res['canal']}"
        assert res["requiere_aprobacion"] is caso["requiere_aprobacion"]
        if res["accion"] == "ENVIO_EXTERNO":
            assert res["codigo_tipo_aprobacion"] == CODIGO_APROBACION_ENVIO_EXTERNO
            assert res["asunto"]
            assert res["borrador_mensaje"]
        else:
            assert res["codigo_tipo_aprobacion"] is None

    def test_precision_global_seguimiento(self):
        total = len(CASOS_DORADOS_SEGUIMIENTO)
        correctos = sum(
            1
            for caso in CASOS_DORADOS_SEGUIMIENTO
            if (
                (r := proponer_seguimiento_deterministico(caso["datos"]))["accion"] == caso["accion_esperada"]
                and r["canal"] == caso["canal_esperado"]
            )
        )
        precision = correctos / total
        assert (
            precision >= PRECISION_MINIMA_CONNECT
        ), f"Precisión connect_seguimiento: {precision:.1%} ({correctos}/{total}), mínimo {PRECISION_MINIMA_CONNECT:.0%}"

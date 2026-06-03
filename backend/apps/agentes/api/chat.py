"""
Asistente conversacional general del ERP (estilo Claude) con streaming SSE
y tool-calling para consultar datos reales del sistema.

POST /api/agentes/chat/  →  recibe {messages:[{role, content}]} y devuelve SSE.
"""
import json
import logging
import os
from datetime import date
from decimal import Decimal

from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
MAX_HISTORY = 20
MAX_TOOL_ROUNDS = 5

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ANTHROPIC_AVAILABLE = False


# ── Serialización segura ───────────────────────────────────────────────────────

def _jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


# ── Contexto de empresa de trabajo (SEC-1) ───────────────────────────────────
# El asistente opera sobre una empresa de trabajo concreta. Por defecto es la
# empresa activa que envía el cliente (validada contra get_empresas_visible); el
# usuario puede pedir cambiarla a otra sobre la que TENGA permisos (tool
# usar_empresa). Nunca se usa la property user.empresa (= empresas.first()), que
# ignora el aislamiento multi-empresa.

def _nombre_empresa(empresa) -> str:
    if empresa is None:
        return "—"
    return (
        getattr(empresa, "nombre_legal", None)
        or getattr(empresa, "nombre_comercial", None)
        or str(empresa)
    )


class _ChatCtx:
    """Contexto mutable de la conversación: usuario, empresa de trabajo y las
    empresas sobre las que el usuario tiene permiso (para validar cambios)."""

    def __init__(self, user, empresa, visibles):
        self.user = user
        self.empresa = empresa
        self.visibles = list(visibles)


# ── Herramientas (datos reales, solo lectura, scoped a la empresa de trabajo) ──

def _tool_tasa_bcv_hoy(ctx, **_):
    from apps.finanzas.models import TasaCambio

    t = (
        TasaCambio.objects.filter(
            fecha_tasa=date.today(),
            tipo_tasa="OFICIAL_BCV",
            id_moneda_origen__codigo_iso="USD",
            id_moneda_destino__codigo_iso="VES",
        )
        .order_by("-fecha_creacion")
        .first()
    )
    if not t:
        return {"resultado": "No hay tasa BCV (USD→VES) registrada para hoy."}
    return {"fecha": str(t.fecha_tasa), "valor_ves_por_usd": str(t.valor_tasa)}


def _tool_aging_cartera(ctx, **_):
    from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider
    from apps.cuentas_por_cobrar.services_aging import calcular_aging

    provider = get_cartera_provider(ctx.empresa)
    resumen = calcular_aging(provider.get_partidas())
    return _jsonable(resumen)


def _tool_buscar_cliente(ctx, termino="", **_):
    from django.db.models import Q
    from apps.crm.models import Cliente

    if not termino:
        return {"error": "Falta el término de búsqueda."}
    qs = (
        Cliente.objects.filter(id_empresa=ctx.empresa, activo=True)
        .filter(
            Q(razon_social__icontains=termino)
            | Q(nombre_comercial__icontains=termino)
            | Q(rif__icontains=termino)
        )[:15]
    )
    clientes = [
        {
            "id_cliente": str(c.id_cliente),
            "razon_social": c.razon_social,
            "nombre_comercial": getattr(c, "nombre_comercial", "") or "",
            "rif": getattr(c, "rif", "") or "",
        }
        for c in qs
    ]
    return {"clientes": clientes, "total": len(clientes)}


def _tool_saldo_cliente(ctx, cliente_id="", **_):
    from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider

    if not cliente_id:
        return {"error": "Falta cliente_id (usa buscar_cliente para obtenerlo)."}
    provider = get_cartera_provider(ctx.empresa)
    partidas = [p for p in provider.get_partidas() if str(p.cliente_id) == str(cliente_id)]
    if not partidas:
        return {"resultado": "El cliente no tiene saldo pendiente."}
    total = sum((p.monto_pendiente for p in partidas), Decimal("0"))
    return {
        "cliente": getattr(partidas[0], "cliente_nombre", ""),
        "total_pendiente": str(total),
        "dias_max_vencido": max(p.dias_vencida for p in partidas),
        "facturas_pendientes": len(partidas),
    }


def _tool_listar_empresas(ctx, **_):
    """Empresas sobre las que el usuario puede trabajar + la empresa actual."""
    return {
        "empresa_actual": (
            {"id": str(ctx.empresa.id_empresa), "nombre": _nombre_empresa(ctx.empresa)}
            if ctx.empresa else None
        ),
        "empresas_disponibles": [
            {"id": str(e.id_empresa), "nombre": _nombre_empresa(e)} for e in ctx.visibles
        ],
    }


def _tool_usar_empresa(ctx, empresa="", **_):
    """Cambia la empresa de trabajo — SOLO entre las que el usuario tiene permiso."""
    termino = str(empresa).strip()
    if not termino:
        return {"error": "Indica el id o el nombre de la empresa."}
    for e in ctx.visibles:
        if str(e.id_empresa) == termino or termino.lower() in _nombre_empresa(e).lower():
            ctx.empresa = e
            return {
                "ok": True,
                "empresa_actual": {"id": str(e.id_empresa), "nombre": _nombre_empresa(e)},
            }
    return {
        "error": "No tienes permiso sobre esa empresa, o no se encontró por ese nombre/id.",
        "empresas_disponibles": [_nombre_empresa(e) for e in ctx.visibles],
    }


_TOOL_DISPATCH = {
    "tasa_bcv_hoy": _tool_tasa_bcv_hoy,
    "aging_cartera": _tool_aging_cartera,
    "buscar_cliente": _tool_buscar_cliente,
    "saldo_cliente": _tool_saldo_cliente,
    "listar_empresas": _tool_listar_empresas,
    "usar_empresa": _tool_usar_empresa,
}

TOOLS = [
    {
        "name": "tasa_bcv_hoy",
        "description": "Devuelve la tasa de cambio oficial del BCV de hoy (bolívares VES por dólar USD).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "aging_cartera",
        "description": "Resumen de antigüedad de la cartera de cuentas por cobrar (CxC) de la empresa: montos y conteos por bucket (al_dia, 1_30, 31_60, 61_90, mas_90).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "buscar_cliente",
        "description": "Busca clientes de la empresa por nombre/razón social/RIF. Devuelve id_cliente para usarlo en otras herramientas.",
        "input_schema": {
            "type": "object",
            "properties": {"termino": {"type": "string", "description": "Texto a buscar (nombre o RIF)."}},
            "required": ["termino"],
        },
    },
    {
        "name": "saldo_cliente",
        "description": "Saldo pendiente y días de mora de un cliente específico. Requiere cliente_id (obtenido con buscar_cliente).",
        "input_schema": {
            "type": "object",
            "properties": {"cliente_id": {"type": "string"}},
            "required": ["cliente_id"],
        },
    },
    {
        "name": "listar_empresas",
        "description": "Lista las empresas sobre las que el usuario tiene permiso para trabajar y cuál es la empresa actual. Úsala si el usuario pregunta en qué empresas puede trabajar o pide cambiar de empresa.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "usar_empresa",
        "description": "Cambia la empresa de trabajo del asistente a otra sobre la que el usuario TENGA permiso (por id o nombre). Las demás herramientas operarán sobre esa empresa a partir de entonces. Si el usuario no tiene permiso, devuelve error con las empresas disponibles.",
        "input_schema": {
            "type": "object",
            "properties": {"empresa": {"type": "string", "description": "Id o nombre de la empresa destino."}},
            "required": ["empresa"],
        },
    },
]


def _dispatch_tool(name, tool_input, ctx):
    fn = _TOOL_DISPATCH.get(name)
    if not fn:
        return {"error": f"Herramienta desconocida: {name}"}
    try:
        return fn(ctx, **(tool_input or {}))
    except Exception as e:  # noqa: BLE001 - se reporta al modelo, no debe tumbar el stream
        logger.warning("Tool %s falló: %s", name, e)
        return {"error": f"No se pudo ejecutar {name}."}


# ── Prompt y validación ─────────────────────────────────────────────────────────

def _build_system_prompt(user, empresa) -> str:
    empresa_nombre = _nombre_empresa(empresa) if empresa else "la empresa actual"
    nombre = (user.get_full_name() or user.username).strip()

    return (
        "Eres Omni, el asistente de IA integrado en Omni ERP, un sistema de gestión "
        f"empresarial para empresas en Venezuela. Ayudas a {nombre}.\n\n"
        f"Trabajas actualmente sobre la empresa «{empresa_nombre}». Si el usuario te pide "
        "trabajar sobre otra empresa, usa la herramienta usar_empresa (solo funciona si el "
        "usuario tiene permiso sobre ella); usa listar_empresas para ver sus opciones.\n\n"
        "Puedes responder dudas sobre el uso del ERP y, cuando sea útil, consultar datos "
        "REALES del sistema con tus herramientas (tasa BCV, antigüedad de cartera CxC, "
        "búsqueda de clientes y saldo de un cliente). Para el saldo de un cliente, primero "
        "búscalo con buscar_cliente para obtener su id_cliente.\n\n"
        "Módulos: Ventas, Inventario, Finanzas, Cobranza (CxC), Fiscal, Configuración, "
        "Integraciones, Empresas y Usuarios.\n\n"
        "Estilo: responde SIEMPRE en español, claro y conciso. Usa Markdown (listas, negritas, "
        "tablas) cuando ayude. Si indicas dónde hacer algo, usa la ruta del menú (p. ej. "
        "\"Ventas → Pedidos\"). No inventes datos: si una herramienta no devuelve algo, dilo. "
        "Contexto: bolívares (VES), dólares (USD), tasa BCV, IVA e IGTF."
    )


def _sanitize_messages(raw) -> list:
    if not isinstance(raw, list):
        return []
    mensajes = []
    for m in raw[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            mensajes.append({"role": role, "content": content.strip()})
    while mensajes and mensajes[0]["role"] != "user":
        mensajes.pop(0)
    return mensajes


class AsistenteChatView(APIView):
    """Asistente conversacional general con streaming SSE + tool-calling."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.core.viewsets import get_empresas_visible

        mensajes = _sanitize_messages(request.data.get("messages"))
        if not mensajes:
            return Response({"error": "Se requiere al menos un mensaje del usuario."}, status=400)

        user = request.user

        # SEC-1: empresa de trabajo = la activa que envía el cliente, VALIDADA contra
        # las empresas sobre las que el usuario tiene permiso. Sin id explícito → la
        # primera visible (empresa por defecto del usuario).
        visibles = list(get_empresas_visible(user))
        empresa_id = request.data.get("empresa_id")
        if empresa_id:
            empresa = next((e for e in visibles if str(e.id_empresa) == str(empresa_id)), None)
            if empresa is None:
                return Response(
                    {"error": "No tienes permiso para trabajar sobre esa empresa."},
                    status=403,
                )
        else:
            empresa = visibles[0] if visibles else None

        ctx = _ChatCtx(user, empresa, visibles)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        system_prompt = _build_system_prompt(user, empresa)

        def sse(payload: dict) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        def event_stream():
            if not (_ANTHROPIC_AVAILABLE and api_key):
                yield sse({
                    "text": "⚠️ El asistente IA no está configurado en este entorno "
                            "(falta ANTHROPIC_API_KEY). Aun así puedo orientarte: usa el menú "
                            "lateral para navegar entre los módulos del ERP.",
                })
                yield "data: [DONE]\n\n"
                return

            try:
                client = anthropic.Anthropic(api_key=api_key)
                conversation = list(mensajes)

                for _ in range(MAX_TOOL_ROUNDS):
                    with client.messages.stream(
                        model=CHAT_MODEL,
                        max_tokens=MAX_TOKENS,
                        system=system_prompt,
                        tools=TOOLS,
                        messages=conversation,
                    ) as stream:
                        for text in stream.text_stream:
                            yield sse({"text": text})
                        final = stream.get_final_message()

                    if final.stop_reason != "tool_use":
                        break

                    conversation.append({"role": "assistant", "content": final.content})
                    tool_results = []
                    for block in final.content:
                        if getattr(block, "type", None) == "tool_use":
                            result = _dispatch_tool(block.name, block.input, ctx)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(_jsonable(result), ensure_ascii=False),
                            })
                    conversation.append({"role": "user", "content": tool_results})

                yield "data: [DONE]\n\n"
            except Exception:  # pragma: no cover
                logger.exception("Error en asistente de chat")
                yield sse({"error": "Ocurrió un error procesando tu solicitud."})

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

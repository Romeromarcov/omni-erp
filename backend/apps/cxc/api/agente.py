"""
Endpoint de streaming para el Agente IA de Cobranza.
Usa Server-Sent Events (SSE) via StreamingHttpResponse.
Rate limit: 10 llamadas/hora por tenant.
"""
import asyncio
import json
import logging

from django.core.cache import cache
from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.core.viewsets import get_empresas_visible

logger = logging.getLogger(__name__)

RATE_LIMIT_MAX = 10  # llamadas por hora
RATE_LIMIT_WINDOW = 3600  # 1 hora en segundos


def _check_rate_limit(empresa_id: str) -> bool:
    """Retorna True si está dentro del límite, False si lo superó."""
    cache_key = f"cxc:agente:ratelimit:{empresa_id}"
    count = cache.get(cache_key, 0)
    if count >= RATE_LIMIT_MAX:
        return False
    cache.set(cache_key, count + 1, timeout=RATE_LIMIT_WINDOW)
    return True


class CobranzaAgenteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        empresa = get_empresas_visible(request.user).first()
        empresa_id = str(empresa.pk)

        if not _check_rate_limit(empresa_id):
            return Response(
                {"error": f"Límite de {RATE_LIMIT_MAX} llamadas/hora al agente superado."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        accion = request.data.get("accion", "analizar_cartera")
        cliente_id = request.data.get("cliente_id")
        instrucciones = request.data.get("instrucciones", "")
        top_n = int(request.data.get("top_n", 10))

        from apps.cxc.agents.cobranza_agent import CobranzaAgent
        agente = CobranzaAgent(empresa_id=empresa_id)

        async def _alist(agen):
            result = []
            async for item in agen:
                result.append(item)
            return result

        def generate_sse():
            """Genera eventos SSE desde el streaming del agente."""
            loop = asyncio.new_event_loop()
            try:
                if accion == "gestionar_cliente" and cliente_id:
                    async_gen = agente.gestionar_cliente(
                        cliente_id=cliente_id,
                        instrucciones=instrucciones,
                    )
                else:
                    async_gen = agente.analizar_cartera(top_n=top_n)

                async def run():
                    async for chunk in async_gen:
                        data = json.dumps({"text": chunk})
                        yield f"data: {data}\n\n"
                    yield "data: [DONE]\n\n"

                for event in loop.run_until_complete(_alist(run())):
                    yield event
            except Exception as exc:
                logger.exception("SSE streaming error: %s", exc)
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            finally:
                loop.close()

        response = StreamingHttpResponse(
            generate_sse(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

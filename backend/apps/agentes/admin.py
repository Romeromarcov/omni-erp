from django.contrib import admin

from .models import ConsumoLLM, EjecucionAgente, PrediccionAgente


@admin.register(PrediccionAgente)
class PrediccionAgenteAdmin(admin.ModelAdmin):
    list_display = ["agente", "categoria_predicha", "confianza", "resultado_humano", "fecha_prediccion", "id_empresa"]
    list_filter = ["agente", "resultado_humano", "fecha_prediccion"]
    search_fields = ["input_texto", "categoria_predicha"]
    readonly_fields = ["id_prediccion", "fecha_prediccion", "modelo_llm", "latencia_ms", "alternativas"]
    ordering = ["-fecha_prediccion"]


@admin.register(EjecucionAgente)
class EjecucionAgenteAdmin(admin.ModelAdmin):
    list_display = [
        "id_ejecucion",
        "agente",
        "estado",
        "id_empresa",
        "iniciado_por",
        "fecha_creacion",
        "fecha_inicio",
        "fecha_fin",
    ]
    list_filter = ["agente", "estado", "fecha_creacion"]
    search_fields = ["id_ejecucion", "agente", "estado", "celery_task_id"]
    readonly_fields = [
        "id_ejecucion",
        "id_empresa",
        "agente",
        "estado",
        "celery_task_id",
        "parametros",
        "resultado",
        "mensaje_error",
        "iniciado_por",
        "fecha_creacion",
        "fecha_inicio",
        "fecha_fin",
    ]
    ordering = ["-fecha_creacion"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConsumoLLM)
class ConsumoLLMAdmin(admin.ModelAdmin):
    list_display = [
        "creado_en",
        "id_empresa",
        "proveedor",
        "uso",
        "modelo",
        "tokens_entrada",
        "tokens_salida",
        "costo_estimado_usd",
        "latencia_ms",
    ]
    list_filter = ["proveedor", "uso", "modelo", "creado_en"]
    search_fields = ["id_consumo", "proveedor", "uso", "modelo"]
    readonly_fields = [
        "id_consumo",
        "id_empresa",
        "proveedor",
        "uso",
        "modelo",
        "tokens_entrada",
        "tokens_salida",
        "costo_estimado_usd",
        "latencia_ms",
        "creado_en",
    ]
    ordering = ["-creado_en"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

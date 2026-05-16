from django.contrib import admin
from .models import PrediccionAgente


@admin.register(PrediccionAgente)
class PrediccionAgenteAdmin(admin.ModelAdmin):
    list_display = ["agente", "categoria_predicha", "confianza", "resultado_humano", "fecha_prediccion", "id_empresa"]
    list_filter = ["agente", "resultado_humano", "fecha_prediccion"]
    search_fields = ["input_texto", "categoria_predicha"]
    readonly_fields = ["id_prediccion", "fecha_prediccion", "modelo_llm", "latencia_ms", "alternativas"]
    ordering = ["-fecha_prediccion"]

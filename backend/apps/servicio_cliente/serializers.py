from rest_framework import serializers

from . import models

# Serializadores para servicio_cliente
# Ejemplo:
# class TuModeloSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.TuModelo
#         fields = '__all__'

# Serializadores agregados automáticamente


class CategoriaTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CategoriaTicket
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_categoria_ticket",
            "nombre_categoria",
            "descripcion",
            "activo",
            "id_empresa",
        ]


class TicketSoporteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TicketSoporte
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_ticket",
            "numero_ticket",
            "asunto",
            "descripcion",
            "id_cliente_temp",
            "id_usuario_reporta_temp",
            "prioridad",
            "estado_ticket",
            "id_agente_asignado_temp",
            "fecha_apertura",
            "fecha_ultima_actualizacion",
            "fecha_cierre",
            "sla_vencimiento",
            "id_empresa",
            "id_categoria_ticket",
        ]


class InteraccionTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.InteraccionTicket
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_interaccion",
            "fecha_hora_interaccion",
            "tipo_interaccion",
            "id_usuario_interactor_temp",
            "contenido",
            "fecha_creacion",
            "id_ticket",
        ]


class BaseConocimientoArticuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BaseConocimientoArticulo
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_articulo",
            "titulo",
            "contenido",
            "palabras_clave",
            "fecha_publicacion",
            "fecha_ultima_revision",
            "activo",
            "visibilidad",
            "id_empresa",
            "id_categoria_ticket",
        ]


class FeedbackClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeedbackCliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_feedback",
            "id_cliente_temp",
            "fecha_feedback",
            "calificacion",
            "comentarios",
            "tipo_feedback",
            "id_empresa",
            "id_ticket_origen",
        ]

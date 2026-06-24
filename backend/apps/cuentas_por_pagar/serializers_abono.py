from rest_framework import serializers

from .models import AbonoCxP


class AbonoCxPSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbonoCxP
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915), en vez
        # de "__all__". El viewset es de solo lectura; estos campos se exponen
        # para list/retrieve del historial de abonos.
        fields = [
            "id_abono_cxp",
            "cuenta_por_pagar",
            "monto",
            "fecha_abono",
            "usuario",
            "descripcion",
            "referencia_externa",
        ]

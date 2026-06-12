"""
Serializers de pagos de contribuciones parafiscales — Capa B §6.7.

``estado``, ``fecha_pago``, ``id_pago`` y ``referencia`` (que fija la acción
``pagar``) son de SOLO lectura: el ciclo de vida se maneja únicamente con las
acciones del ViewSet (pagar / anular), nunca con un PATCH directo.
"""

from decimal import Decimal

from django.db.models import Q

from rest_framework import serializers

from .models import ContribucionParafiscal, PagoContribucionParafiscal


class PagoContribucionParafiscalSerializer(serializers.ModelSerializer):
    contribucion_codigo = serializers.CharField(
        source="contribucion.codigo", read_only=True, default=None
    )
    contribucion_nombre = serializers.CharField(
        source="contribucion.nombre", read_only=True, default=None
    )
    moneda_codigo = serializers.CharField(
        source="id_moneda.codigo_iso", read_only=True, default=None
    )
    periodo = serializers.CharField(read_only=True)

    class Meta:
        model = PagoContribucionParafiscal
        fields = [
            "id_pago_parafiscal",
            "id_empresa",
            "contribucion",
            "contribucion_codigo",
            "contribucion_nombre",
            "periodo_año",
            "periodo_mes",
            "periodo",
            "monto",
            "id_moneda",
            "moneda_codigo",
            "referencia",
            "id_proceso_nomina",
            "estado",
            "fecha_pago",
            "id_pago",
            "referencia_externa",
            "documento_json",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_pago_parafiscal",
            "estado",
            "fecha_pago",
            "id_pago",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        # El validador que DRF autogenera para el UniqueConstraint condicional
        # lanza KeyError en PATCH (la condición usa 'estado', que es read-only)
        # y pisa el mensaje amable de validate(). La regla de no-doble-pago la
        # aplican validate() (mensaje claro) + la constraint de BD (backstop de
        # carreras, traducida a 400 en el ViewSet).
        validators = []

    def validate_monto(self, value):
        if value is None or Decimal(str(value)) <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value

    def validate_periodo_mes(self, value):
        if not 1 <= value <= 12:
            raise serializers.ValidationError("El mes del período debe estar entre 1 y 12.")
        return value

    def validate_periodo_año(self, value):
        if not 2000 <= value <= 2100:
            raise serializers.ValidationError("El año del período debe estar entre 2000 y 2100.")
        return value

    def validate(self, attrs):
        # Un registro que ya movió dinero (pagado) o se cerró (anulado) es
        # INMUTABLE por PATCH/PUT: su historia financiera no se reescribe.
        if self.instance is not None and self.instance.estado != "pendiente":
            raise serializers.ValidationError(
                {
                    "detail": (
                        f"Un pago parafiscal en estado '{self.instance.estado}' no es "
                        "editable. Use las acciones del ciclo de vida."
                    )
                }
            )

        empresa = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        contribucion = attrs.get("contribucion") or getattr(self.instance, "contribucion", None)
        proceso = attrs.get("id_proceso_nomina") or getattr(
            self.instance, "id_proceso_nomina", None
        )

        # R-CODE-1: la contribución debe ser de la MISMA empresa, global
        # (empresa=None) o pública — espejo de Pago._validar_documento.
        # (TenantFKScopeMixin ya acota a empresas visibles + filas globales;
        # esto cierra el caso de un usuario con varias empresas visibles.)
        if empresa is not None and contribucion is not None:
            accesible = ContribucionParafiscal.objects.filter(
                Q(empresa_id=empresa.pk) | Q(empresa__isnull=True) | Q(es_publico=True)
            ).filter(pk=contribucion.pk).exists()
            if not accesible:
                raise serializers.ValidationError(
                    {"contribucion": "La contribución no está disponible para la empresa indicada."}
                )

        # R-CODE-1: el proceso de nómina (trazabilidad) debe ser del tenant.
        if empresa is not None and proceso is not None:
            if str(proceso.id_empresa_id) != str(empresa.pk):
                raise serializers.ValidationError(
                    {"id_proceso_nomina": "El proceso de nómina no pertenece a la empresa indicada."}
                )

        # No doble pago (mensaje amable; la constraint condicional de BD es el
        # backstop ante carreras): solo una fila NO anulada por período.
        año = attrs.get("periodo_año", getattr(self.instance, "periodo_año", None))
        mes = attrs.get("periodo_mes", getattr(self.instance, "periodo_mes", None))
        if empresa is not None and contribucion is not None and año and mes:
            existentes = PagoContribucionParafiscal.objects.filter(
                id_empresa=empresa,
                contribucion=contribucion,
                periodo_año=año,
                periodo_mes=mes,
            ).exclude(estado="anulado")
            if self.instance is not None:
                existentes = existentes.exclude(pk=self.instance.pk)
            if existentes.exists():
                raise serializers.ValidationError(
                    {
                        "detail": (
                            f"Ya existe un pago de {contribucion.codigo} para el período "
                            f"{año:04d}-{mes:02d} (no anulado). No se permite el doble pago "
                            "del mismo período + contribución."
                        )
                    }
                )
        return attrs

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.finanzas.ajustes import crear_ajuste_caja_banco
from apps.finanzas.models import MovimientoCajaBanco
from apps.core.models import Empresa, Usuarios
from apps.finanzas.models import Moneda, Caja, CuentaBancariaEmpresa
from rest_framework import serializers

class AjusteCajaBancoSerializer(serializers.Serializer):
    empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all())
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)
    moneda = serializers.PrimaryKeyRelatedField(queryset=Moneda.objects.all())
    caja = serializers.PrimaryKeyRelatedField(queryset=Caja.objects.all(), required=False, allow_null=True)
    cuenta_bancaria = serializers.PrimaryKeyRelatedField(queryset=CuentaBancariaEmpresa.objects.all(), required=False, allow_null=True)
    usuario = serializers.PrimaryKeyRelatedField(queryset=Usuarios.objects.all())
    motivo = serializers.CharField(max_length=255, required=False, allow_blank=True)
    tipo_ajuste = serializers.ChoiceField(choices=[('POSITIVO', 'Ajuste Positivo'), ('NEGATIVO', 'Ajuste Negativo')])
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True)

class AjusteCajaBancoViewSet(viewsets.ViewSet):
    @action(detail=False, methods=['post'])
    def crear_ajuste(self, request):
        serializer = AjusteCajaBancoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movimiento = crear_ajuste_caja_banco(**serializer.validated_data)
        return Response({'id_movimiento': movimiento.id_movimiento}, status=status.HTTP_201_CREATED)

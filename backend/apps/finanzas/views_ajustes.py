from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import Empresa, Usuarios
from apps.finanzas.ajustes import crear_ajuste_caja_banco
from apps.finanzas.models import Caja, CuentaBancariaEmpresa, Moneda


class AjusteCajaBancoSerializer(serializers.Serializer):
    empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all())
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)
    moneda = serializers.PrimaryKeyRelatedField(queryset=Moneda.objects.all())
    caja = serializers.PrimaryKeyRelatedField(queryset=Caja.objects.all(), required=False, allow_null=True)
    cuenta_bancaria = serializers.PrimaryKeyRelatedField(
        queryset=CuentaBancariaEmpresa.objects.all(), required=False, allow_null=True
    )
    usuario = serializers.PrimaryKeyRelatedField(queryset=Usuarios.objects.all())
    motivo = serializers.CharField(max_length=255, required=False, allow_blank=True)
    tipo_ajuste = serializers.ChoiceField(choices=[("POSITIVO", "Ajuste Positivo"), ("NEGATIVO", "Ajuste Negativo")])
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate(self, attrs):
        from rest_framework.exceptions import PermissionDenied

        from apps.core.viewsets import get_empresas_visible

        empresa = attrs["empresa"]
        caja = attrs.get("caja")
        cuenta_bancaria = attrs.get("cuenta_bancaria")
        moneda = attrs["moneda"]
        usuario = attrs["usuario"]

        request = self.context.get("request")
        visible_ids = None
        es_super = False
        if request is not None and getattr(request, "user", None) and request.user.is_authenticated:
            es_super = getattr(request.user, "es_superusuario_omni", False)
            visible_ids = set(get_empresas_visible(request.user).values_list("id_empresa", flat=True))
            if not es_super and empresa.id_empresa not in visible_ids:
                raise PermissionDenied("No tiene permiso para operar sobre la empresa especificada.")

        if caja is not None and caja.empresa_id != empresa.id_empresa:
            if visible_ids is not None and not es_super and caja.empresa_id not in visible_ids:
                raise PermissionDenied("No tiene permiso sobre la caja especificada.")
            raise serializers.ValidationError({"caja": "La caja no pertenece a la empresa indicada."})

        if cuenta_bancaria is not None and cuenta_bancaria.id_empresa_id != empresa.id_empresa:
            if visible_ids is not None and not es_super and cuenta_bancaria.id_empresa_id not in visible_ids:
                raise PermissionDenied("No tiene permiso sobre la cuenta bancaria especificada.")
            raise serializers.ValidationError(
                {"cuenta_bancaria": "La cuenta bancaria no pertenece a la empresa indicada."}
            )

        if not moneda.es_generica and not moneda.es_publica and moneda.empresa_id != empresa.id_empresa:
            if visible_ids is not None and not es_super and moneda.empresa_id not in visible_ids:
                raise PermissionDenied("No tiene permiso sobre la moneda especificada.")
            raise serializers.ValidationError({"moneda": "La moneda no pertenece a la empresa indicada."})

        if not getattr(usuario, "es_superusuario_omni", False):
            usuario_visible_ids = set(get_empresas_visible(usuario).values_list("id_empresa", flat=True))
            if empresa.id_empresa not in usuario_visible_ids:
                raise PermissionDenied("El usuario no pertenece a la empresa indicada.")

        return attrs


class AjusteCajaBancoViewSet(viewsets.ViewSet):
    @action(detail=False, methods=["post"])
    def crear_ajuste(self, request):
        serializer = AjusteCajaBancoSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        movimiento = crear_ajuste_caja_banco(**serializer.validated_data)
        return Response({"id_movimiento": movimiento.id_movimiento}, status=status.HTTP_201_CREATED)

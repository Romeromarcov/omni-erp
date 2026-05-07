from rest_framework import serializers
from .models import (
    Impuesto, ConfiguracionImpuesto, Retencion, ContribucionParafiscal,
    ImpuestoEmpresaActiva, RetencionEmpresaActiva, ContribucionEmpresaActiva,
    EmpresaContribucionParafiscal, ConfiguracionRetencion
)

class ImpuestoSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    class Meta:
        model = Impuesto
        fields = '__all__'
        read_only_fields = ['empresa_nombre']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        user = self.context.get('request').user if self.context.get('request') else None
        if not getattr(user, 'es_superusuario_omni', False):
            rep.pop('es_generico', None)
            rep.pop('empresa', None)
        return rep

    def validate(self, data):
        user = self.context['request'].user if 'request' in self.context else None
        # Solo superusuario puede modificar impuestos genéricos
        if self.instance and getattr(self.instance, 'es_generico', False) and not getattr(user, 'es_superusuario_omni', False):
            raise serializers.ValidationError('No puede modificar un impuesto genérico del sistema.')
        # Solo superusuario puede marcar como genérico o público o cambiar empresa
        if (data.get('es_generico') or data.get('es_publico') or data.get('empresa')) and not getattr(user, 'es_superusuario_omni', False):
            raise serializers.ValidationError('Solo el superusuario puede crear o modificar impuestos genéricos, públicos o de otra empresa.')
        # Validar unicidad de codigo por empresa si no es genérico
        es_generico = data.get('es_generico', getattr(self.instance, 'es_generico', False))
        empresa = data.get('empresa', getattr(self.instance, 'empresa', None))
        codigo = data.get('codigo', getattr(self.instance, 'codigo', None))
        from .models import Impuesto
        if not es_generico and empresa and codigo:
            qs = Impuesto.objects.filter(codigo=codigo, es_generico=False, empresa=empresa)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'codigo': 'Ya existe un impuesto con este código para esta empresa.'})
        return data

    def create(self, validated_data):
        user = self.context['request'].user if 'request' in self.context else None
        if not getattr(user, 'es_superusuario_omni', False):
            empresas = user.empresas.all()
            validated_data['empresa'] = empresas.first() if empresas.exists() else None
            validated_data['es_generico'] = False
            validated_data['es_publico'] = False
        return super().create(validated_data)

    def update(self, instance, validated_data):
        user = self.context['request'].user if 'request' in self.context else None
        if not getattr(user, 'es_superusuario_omni', False):
            validated_data.pop('empresa', None)
            validated_data.pop('es_generico', None)
            validated_data.pop('es_publico', None)
        return super().update(instance, validated_data)

class ConfiguracionImpuestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionImpuesto
        fields = '__all__'

class RetencionSerializer(serializers.ModelSerializer):
    agente_retencion_nombre = serializers.CharField(source='agente_retencion.nombre_comercial', read_only=True)
    sujeto_retenido_nombre = serializers.CharField(source='sujeto_retenido.nombre_comercial', read_only=True)
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    class Meta:
        model = Retencion
        fields = '__all__'
        read_only_fields = ['agente_retencion_nombre', 'sujeto_retenido_nombre', 'empresa_nombre']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        user = self.context.get('request').user if self.context.get('request') else None
        if not getattr(user, 'es_superusuario_omni', False):
            rep.pop('es_generico', None)
            rep.pop('empresa', None)
        return rep

    def validate(self, data):
        user = self.context['request'].user if 'request' in self.context else None
        if self.instance and getattr(self.instance, 'es_generico', False) and not getattr(user, 'es_superusuario_omni', False):
            raise serializers.ValidationError('No puede modificar una retención genérica del sistema.')
        if (data.get('es_generico') or data.get('es_publico') or data.get('empresa')) and not getattr(user, 'es_superusuario_omni', False):
            raise serializers.ValidationError('Solo el superusuario puede crear o modificar retenciones genéricas, públicas o de otra empresa.')
        es_generico = data.get('es_generico', getattr(self.instance, 'es_generico', False))
        empresa = data.get('empresa', getattr(self.instance, 'empresa', None))
        codigo = data.get('codigo', getattr(self.instance, 'codigo', None))
        from .models import Retencion
        if not es_generico and empresa and codigo:
            qs = Retencion.objects.filter(codigo=codigo, es_generico=False, empresa=empresa)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'codigo': 'Ya existe una retención con este código para esta empresa.'})
        return data

    def create(self, validated_data):
        user = self.context['request'].user if 'request' in self.context else None
        if not getattr(user, 'es_superusuario_omni', False):
            empresas = user.empresas.all()
            validated_data['empresa'] = empresas.first() if empresas.exists() else None
            validated_data['es_generico'] = False
            validated_data['es_publico'] = False
        return super().create(validated_data)

    def update(self, instance, validated_data):
        user = self.context['request'].user if 'request' in self.context else None
        if not getattr(user, 'es_superusuario_omni', False):
            validated_data.pop('empresa', None)
            validated_data.pop('es_generico', None)
            validated_data.pop('es_publico', None)
        return super().update(instance, validated_data)

class ContribucionParafiscalSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    class Meta:
        model = ContribucionParafiscal
        fields = '__all__'
        read_only_fields = ['empresa_nombre']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        user = self.context.get('request').user if self.context.get('request') else None
        if not getattr(user, 'es_superusuario_omni', False):
            rep.pop('es_generico', None)
            rep.pop('empresa', None)
        return rep

    def validate(self, data):
        user = self.context['request'].user if 'request' in self.context else None
        if self.instance and getattr(self.instance, 'es_generico', False) and not getattr(user, 'es_superusuario_omni', False):
            raise serializers.ValidationError('No puede modificar una contribución genérica del sistema.')
        if (data.get('es_generico') or data.get('es_publico') or data.get('empresa')) and not getattr(user, 'es_superusuario_omni', False):
            raise serializers.ValidationError('Solo el superusuario puede crear o modificar contribuciones genéricas, públicas o de otra empresa.')
        es_generico = data.get('es_generico', getattr(self.instance, 'es_generico', False))
        empresa = data.get('empresa', getattr(self.instance, 'empresa', None))
        codigo = data.get('codigo', getattr(self.instance, 'codigo', None))
        from .models import ContribucionParafiscal
        if not es_generico and empresa and codigo:
            qs = ContribucionParafiscal.objects.filter(codigo=codigo, es_generico=False, empresa=empresa)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'codigo': 'Ya existe una contribución con este código para esta empresa.'})
        return data

    def create(self, validated_data):
        user = self.context['request'].user if 'request' in self.context else None
        if not getattr(user, 'es_superusuario_omni', False):
            empresas = user.empresas.all()
            validated_data['empresa'] = empresas.first() if empresas.exists() else None
            validated_data['es_generico'] = False
            validated_data['es_publico'] = False
        return super().create(validated_data)

    def update(self, instance, validated_data):
        user = self.context['request'].user if 'request' in self.context else None
        if not getattr(user, 'es_superusuario_omni', False):
            validated_data.pop('empresa', None)
            validated_data.pop('es_generico', None)
            validated_data.pop('es_publico', None)
        return super().update(instance, validated_data)

class ImpuestoEmpresaActivaSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    impuesto_codigo = serializers.CharField(source='impuesto.codigo', read_only=True)
    impuesto_nombre = serializers.CharField(source='impuesto.nombre', read_only=True)
    class Meta:
        model = ImpuestoEmpresaActiva
        fields = ['id', 'empresa', 'empresa_nombre', 'impuesto', 'impuesto_codigo', 'impuesto_nombre', 'activa']
        read_only_fields = ['empresa_nombre', 'impuesto_codigo', 'impuesto_nombre']

class RetencionEmpresaActivaSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    retencion_codigo = serializers.CharField(source='retencion.codigo', read_only=True)
    retencion_nombre = serializers.CharField(source='retencion.nombre', read_only=True)
    class Meta:
        model = RetencionEmpresaActiva
        fields = ['id', 'empresa', 'empresa_nombre', 'retencion', 'retencion_codigo', 'retencion_nombre', 'activa']
        read_only_fields = ['empresa_nombre', 'retencion_codigo', 'retencion_nombre']

class ContribucionEmpresaActivaSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    contribucion_codigo = serializers.CharField(source='contribucion.codigo', read_only=True)
    contribucion_nombre = serializers.CharField(source='contribucion.nombre', read_only=True)
    class Meta:
        model = ContribucionEmpresaActiva
        fields = ['id', 'empresa', 'empresa_nombre', 'contribucion', 'contribucion_codigo', 'contribucion_nombre', 'activa']
        read_only_fields = ['empresa_nombre', 'contribucion_codigo', 'contribucion_nombre']

class EmpresaContribucionParafiscalSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre_comercial', read_only=True)
    contribucion_nombre = serializers.CharField(source='contribucion.nombre', read_only=True)
    class Meta:
        model = EmpresaContribucionParafiscal
        fields = '__all__'
        read_only_fields = ['empresa_nombre', 'contribucion_nombre']

class ConfiguracionRetencionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionRetencion
        fields = '__all__'

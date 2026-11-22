"""Serializers de entrada para OpenAPI/Schemathesis de apps.sync (CTF-008)."""

from rest_framework import serializers


class SyncMutacionInputSerializer(serializers.Serializer):
    entity = serializers.CharField(max_length=64)
    id = serializers.UUIDField()
    expected_fecha_actualizacion = serializers.CharField(max_length=64)
    cambios = serializers.DictField()


class SyncPushInputSerializer(serializers.Serializer):
    entity = serializers.CharField(max_length=64, required=False)
    id = serializers.UUIDField(required=False)
    expected_fecha_actualizacion = serializers.CharField(max_length=64, required=False)
    cambios = serializers.DictField(required=False)
    mutaciones = SyncMutacionInputSerializer(many=True, required=False)

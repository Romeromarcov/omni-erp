# Validadores reutilizables para modelos y serializers
from django.core.exceptions import ValidationError


def validate_positive(value):
    if value < 0:
        raise ValidationError("El valor debe ser positivo.")


def validar_misma_empresa(instancia, **relacionados):
    """Rechaza FKs que apunten a registros de otra empresa (R-CODE-1).

    ``relacionados`` mapea nombre de campo -> objeto relacionado (o ``None``).
    Cada objeto debe exponer ``id_empresa_id``; se compara contra el de
    ``instancia``. RLS valida la empresa de la fila propia, no la de sus FKs:
    esta comprobación cubre ese hueco. Corre en ``full_clean()``, por lo que
    los servicios que crean registros deben invocarlo (no basta ``objects.create``).
    """
    errores = {}
    for campo, obj in relacionados.items():
        if obj is None:
            continue
        if getattr(obj, "id_empresa_id", None) != instancia.id_empresa_id:
            errores[campo] = "Debe pertenecer a la misma empresa."
    if errores:
        raise ValidationError(errores)

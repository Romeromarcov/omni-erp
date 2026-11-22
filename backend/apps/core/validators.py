# Validadores reutilizables para modelos y serializers
import re

from django.core.exceptions import ValidationError


def normalizar_email(value: str | None) -> str:
    """Normaliza correo electrónico (minúsculas y sin espacios laterales)."""
    return (value or "").strip().lower()[:254]


def normalizar_telefono(value: str | None, codigo_pais_default: str = "58") -> str:
    """Normaliza teléfono a dígitos E.164 sin separadores (máx. 20 dígitos)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    tiene_mas = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if not tiene_mas:
        if digits.startswith("00") and len(digits) > 2:
            digits = digits[2:]
        elif digits.startswith("0") and codigo_pais_default:
            digits = f"{codigo_pais_default}{digits[1:]}"
    return digits[:20]


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

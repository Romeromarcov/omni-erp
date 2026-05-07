# Validadores reutilizables para modelos y serializers
from django.core.exceptions import ValidationError

def validate_positive(value):
    if value < 0:
        raise ValidationError('El valor debe ser positivo.')

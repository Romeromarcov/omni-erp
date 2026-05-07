# Backend ERP - Mejores Prácticas

## Estructura
- apps/: Cada dominio como app Django independiente
- config/: Configuración desacoplada (base, dev, prod)
- core/: Clases base, permisos, validadores, señales

## Configuración
- Usa `.env` para variables sensibles
- Cambia el entorno con `DJANGO_ENV=dev` o `prod`

## Comandos útiles
- `python manage.py makemigrations`
- `python manage.py migrate`
- `python manage.py createsuperuser`

## Documentación API
- Accede a `/swagger/` para la documentación interactiva

## Tests
- Ejecuta `python manage.py test` para correr los tests

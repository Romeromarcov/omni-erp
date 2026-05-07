#!/usr/bin/env python
import os
import sys
import django
from django.test import Client, override_settings
from django.contrib.auth import get_user_model

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

# Crear cliente de prueba con ALLOWED_HOSTS override
with override_settings(ALLOWED_HOSTS=['testserver']):
    client = Client()

    # Obtener un usuario para autenticar
    User = get_user_model()
    user = User.objects.filter(is_active=True).first()
    if user:
        client.force_login(user)
        print(f'Usuario autenticado: {user.username}')

        # Hacer petición a la API
        empresa_id = '44444444-4444-4444-4444-444444444444'
        response = client.get(f'/api/finanzas/transacciones-financieras/?id_empresa={empresa_id}')
        print(f'Status code: {response.status_code}')
        print(f'Content-Type: {response.get("Content-Type")}')

        if response.status_code == 200:
            data = response.json()
            print(f'Tipo de respuesta: {type(data)}')
            if isinstance(data, list):
                print(f'Número de transacciones devueltas: {len(data)}')
                if len(data) > 0:
                    print('Primera transacción:')
                    for key, value in data[0].items():
                        print(f'  {key}: {value}')
            elif isinstance(data, dict) and 'results' in data:
                results = data['results']
                print(f'Número de transacciones devueltas: {len(results)}')
                if len(results) > 0:
                    print('Primera transacción:')
                    for key, value in results[0].items():
                        print(f'  {key}: {value}')
            else:
                print(f'Respuesta inesperada: {data}')
        else:
            print(f'Error: {response.content.decode()[:500]}')
    else:
        print('No se encontró usuario activo')
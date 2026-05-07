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
    try:
        user = User.objects.filter(is_active=True).first()
        if user:
            client.force_login(user)
            print(f'Usuario autenticado: {user.username}')

            # Hacer petición a la API
            response = client.get('/api/finanzas/transacciones-financieras/?id_empresa=44444444-4444-4444-4444-444444444444')
            print(f'Status code: {response.status_code}')
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    print(f'Resultados: {len(data)} transacciones')
                    if len(data) > 0:
                        print(f'Primera transacción: ID={data[0].get("id_transaccion")}, Tipo={data[0].get("tipo_transaccion")}')
                elif isinstance(data, dict) and 'results' in data:
                    results = data['results']
                    print(f'Resultados: {len(results)} transacciones')
                    if len(results) > 0:
                        print(f'Primera transacción: ID={results[0].get("id_transaccion")}, Tipo={results[0].get("tipo_transaccion")}')
                else:
                    print(f'Data inesperada: {type(data)}')
            else:
                print(f'Error: {response.content.decode()[:200]}')
        else:
            print('No se encontró usuario activo')
    except Exception as e:
        print(f'Error: {e}')
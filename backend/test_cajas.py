#!/usr/bin/env python
import os
import sys
import django

# Agregar el directorio backend al path
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django.setup()

from django.test import Client
from apps.core.models import Usuarios

def test_endpoint():
    client = Client()
    usuario = Usuarios.objects.filter(username='admin').first()
    print(f'Usuario: {usuario.username}')

    login_success = client.login(username='admin', password='admin123')
    print(f'Login: {login_success}')

    response = client.get('/api/finanzas/cajas-usuario/')
    print(f'Status: {response.status_code}')

    if response.status_code == 200:
        data = response.json()
        results = data.get('results', [])
        print(f'Cajas disponibles: {len(results)}')
        for i, caja in enumerate(results):
            print(f'Caja {i+1}:')
            for key, value in caja.items():
                print(f'  {key}: {value}')
            print()
    else:
        print(f'Error: {response.content.decode()}')

if __name__ == '__main__':
    test_endpoint()
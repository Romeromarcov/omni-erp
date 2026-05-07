#!/usr/bin/env python
import os
import sys
import django
import json

# Agregar el directorio backend al path
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django.setup()

from django.test import Client
from apps.core.models import Usuarios, Empresa
from apps.crm.models import Cliente
from apps.inventario.models import Producto

def test_pedido_con_pagos():
    client = Client()
    usuario = Usuarios.objects.filter(username='admin').first()

    # Login
    login_success = client.login(username='admin', password='admin123')
    print(f'Login exitoso: {login_success}')

    # Obtener datos necesarios
    empresa = Empresa.objects.first()
    cliente = Cliente.objects.first()
    producto = Producto.objects.first()

    print(f'Empresa: {empresa.nombre_legal if empresa else "None"}')
    print(f'Cliente: {cliente.razon_social if cliente else "None"}')
    print(f'Producto: {producto.nombre_producto if producto else "None"}')

    if not all([empresa, cliente, producto]):
        print("Faltan datos básicos para crear el pedido")
        return

    # Crear datos de pedido simples
    from datetime import datetime
    pedido_data = {
        'fecha_pedido': datetime.now().strftime('%Y-%m-%d'),
        'id_empresa': str(empresa.id_empresa),
        'id_cliente': str(cliente.id_cliente),
        'detalles': [{
            'id_producto': str(producto.id_producto),
            'cantidad': '1',
            'precio_unitario': '100.00',
            'subtotal': '100.00'  # Agregar subtotal
        }],
        'pagos': [{
            'metodo': 'EFECTIVO',
            'moneda': 'VES',
            'monto': '50.00',
            'tasa': '1.0',
            'id_caja_virtual': '4da64931-faa8-4130-8ade-6bd8446679bf'  # Caja VES
        }, {
            'metodo': 'Pago Movil',
            'moneda': 'VES',
            'monto': '50.00',
            'tasa': '1.0'
        }]
    }

    print('Enviando datos del pedido:')
    print(json.dumps(pedido_data, indent=2))

    # Enviar la petición POST
    response = client.post(
        '/api/ventas/pedidos/',
        data=json.dumps(pedido_data),
        content_type='application/json'
    )

    print(f'Status code: {response.status_code}')
    if response.status_code == 201:
        print('Pedido creado exitosamente')
        print('Respuesta:', response.json())
    else:
        print('Error al crear pedido')
        print('Respuesta:', response.content.decode())

if __name__ == '__main__':
    test_pedido_con_pagos()
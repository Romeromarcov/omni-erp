"""
Dataset de evaluación para el clasificador de gastos.
50 casos dorados: (descripcion, monto_usd, categoria_esperada)

Estos casos son la fuente de verdad para medir la calidad del agente.
El runner en tests verifica que la precisión sea >= PRECISION_MINIMA.
"""

from decimal import Decimal

PRECISION_MINIMA = 0.80  # El agente debe acertar >= 80% de los casos

CATEGORIAS_CANONICAS = [
    "alimentacion",
    "transporte",
    "alojamiento",
    "materiales_oficina",
    "servicios_profesionales",
    "tecnologia_software",
    "marketing_publicidad",
    "mantenimiento_reparacion",
    "servicios_publicos",
    "comunicaciones",
    "capacitacion_formacion",
    "salud_bienestar",
    "impuestos_tasas",
    "otros",
]

CASOS_DORADOS = [
    # alimentacion (10 casos)
    {"descripcion": "Almuerzo de trabajo con cliente", "monto": Decimal("45.00"), "categoria": "alimentacion"},
    {"descripcion": "Cena equipo de ventas", "monto": Decimal("120.00"), "categoria": "alimentacion"},
    {"descripcion": "Café y desayuno reunión de directivos", "monto": Decimal("18.50"), "categoria": "alimentacion"},
    {"descripcion": "Catering para evento corporativo", "monto": Decimal("350.00"), "categoria": "alimentacion"},
    {"descripcion": "Snacks para oficina", "monto": Decimal("25.00"), "categoria": "alimentacion"},
    {"descripcion": "Comida para capacitación interna", "monto": Decimal("80.00"), "categoria": "alimentacion"},
    {"descripcion": "Lunch box para trabajo remoto", "monto": Decimal("15.00"), "categoria": "alimentacion"},
    {"descripcion": "Restaurante visita a proveedor", "monto": Decimal("67.00"), "categoria": "alimentacion"},
    {"descripcion": "Agua y refrescos para sala de juntas", "monto": Decimal("12.00"), "categoria": "alimentacion"},
    {"descripcion": "Pizza de cierre de proyecto", "monto": Decimal("55.00"), "categoria": "alimentacion"},
    # transporte (8 casos)
    {"descripcion": "Pasaje aéreo Caracas-Maracaibo", "monto": Decimal("180.00"), "categoria": "transporte"},
    {"descripcion": "Taxi al aeropuerto", "monto": Decimal("22.00"), "categoria": "transporte"},
    {"descripcion": "Gasolina visita clientes", "monto": Decimal("40.00"), "categoria": "transporte"},
    {"descripcion": "Peaje autopista regional", "monto": Decimal("5.50"), "categoria": "transporte"},
    {"descripcion": "Estacionamiento oficina central", "monto": Decimal("30.00"), "categoria": "transporte"},
    {"descripcion": "Uber para reunión externa", "monto": Decimal("14.00"), "categoria": "transporte"},
    {"descripcion": "Alquiler de vehículo viaje de negocios", "monto": Decimal("220.00"), "categoria": "transporte"},
    {"descripcion": "Metro y transporte público", "monto": Decimal("8.00"), "categoria": "transporte"},
    # alojamiento (4 casos)
    {"descripcion": "Hotel 2 noches congreso nacional", "monto": Decimal("280.00"), "categoria": "alojamiento"},
    {"descripcion": "Airbnb visita sucursal Mérida", "monto": Decimal("95.00"), "categoria": "alojamiento"},
    {"descripcion": "Hospedaje capacitación fuera de ciudad", "monto": Decimal("150.00"), "categoria": "alojamiento"},
    {"descripcion": "Posada visita auditoría", "monto": Decimal("60.00"), "categoria": "alojamiento"},
    # materiales_oficina (4 casos)
    {"descripcion": "Resma de papel bond carta", "monto": Decimal("18.00"), "categoria": "materiales_oficina"},
    {"descripcion": "Tóner impresora HP", "monto": Decimal("75.00"), "categoria": "materiales_oficina"},
    {"descripcion": "Bolígrafos y marcadores", "monto": Decimal("12.00"), "categoria": "materiales_oficina"},
    {"descripcion": "Archivadores y carpetas", "monto": Decimal("30.00"), "categoria": "materiales_oficina"},
    # tecnologia_software (5 casos)
    {"descripcion": "Suscripción mensual Slack", "monto": Decimal("87.00"), "categoria": "tecnologia_software"},
    {"descripcion": "Licencia Adobe Creative Cloud", "monto": Decimal("55.00"), "categoria": "tecnologia_software"},
    {"descripcion": "Servidor VPS DigitalOcean", "monto": Decimal("40.00"), "categoria": "tecnologia_software"},
    {"descripcion": "Dominio y hosting web", "monto": Decimal("25.00"), "categoria": "tecnologia_software"},
    {"descripcion": "Antivirus corporativo renovación", "monto": Decimal("120.00"), "categoria": "tecnologia_software"},
    # servicios_profesionales (4 casos)
    {"descripcion": "Honorarios consultoría legal", "monto": Decimal("500.00"), "categoria": "servicios_profesionales"},
    {"descripcion": "Contabilidad externa mensual", "monto": Decimal("300.00"), "categoria": "servicios_profesionales"},
    {"descripcion": "Diseño gráfico logo empresa", "monto": Decimal("250.00"), "categoria": "servicios_profesionales"},
    {"descripcion": "Auditoría de sistemas externa", "monto": Decimal("800.00"), "categoria": "servicios_profesionales"},
    # marketing_publicidad (3 casos)
    {"descripcion": "Anuncio en Instagram y Facebook", "monto": Decimal("200.00"), "categoria": "marketing_publicidad"},
    {"descripcion": "Impresión de folletos promocionales", "monto": Decimal("90.00"), "categoria": "marketing_publicidad"},
    {"descripcion": "Patrocinio evento gremial", "monto": Decimal("400.00"), "categoria": "marketing_publicidad"},
    # mantenimiento_reparacion (3 casos)
    {"descripcion": "Reparación aire acondicionado oficina", "monto": Decimal("180.00"), "categoria": "mantenimiento_reparacion"},
    {"descripcion": "Mantenimiento preventivo flota", "monto": Decimal("350.00"), "categoria": "mantenimiento_reparacion"},
    {"descripcion": "Cambio de cerraduras edificio", "monto": Decimal("120.00"), "categoria": "mantenimiento_reparacion"},
    # servicios_publicos (3 casos)
    {"descripcion": "Factura eléctrica mes de octubre", "monto": Decimal("55.00"), "categoria": "servicios_publicos"},
    {"descripcion": "Agua potable y cloacas", "monto": Decimal("20.00"), "categoria": "servicios_publicos"},
    {"descripcion": "Gas doméstico oficina", "monto": Decimal("15.00"), "categoria": "servicios_publicos"},
    # comunicaciones (2 casos)
    {"descripcion": "Plan corporativo móvil 5 líneas", "monto": Decimal("120.00"), "categoria": "comunicaciones"},
    {"descripcion": "Internet fibra óptica sede principal", "monto": Decimal("80.00"), "categoria": "comunicaciones"},
    # capacitacion_formacion (2 casos)
    {"descripcion": "Curso online certificación PMP", "monto": Decimal("350.00"), "categoria": "capacitacion_formacion"},
    {"descripcion": "Taller liderazgo para gerentes", "monto": Decimal("600.00"), "categoria": "capacitacion_formacion"},
    # impuestos_tasas (2 casos)
    {"descripcion": "Impuesto municipal actividades económicas", "monto": Decimal("200.00"), "categoria": "impuestos_tasas"},
    {"descripcion": "Timbres fiscales contratos", "monto": Decimal("45.00"), "categoria": "impuestos_tasas"},
]

assert len(CASOS_DORADOS) == 50, f"Se esperaban 50 casos, hay {len(CASOS_DORADOS)}"

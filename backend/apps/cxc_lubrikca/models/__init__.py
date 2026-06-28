"""Modelos del subproyecto CxC Lubrikca.

Se poblarán por fase (ver PLAN_TRABAJO.md):
- Fase 1: modelos de configuración del motor con *effective dating*
  (DescuentoMarcaCategoria, DescuentoBCVCompleto, PromocionPrimeraCompra,
  ReglaRecurrencia, Feriado, LimiteDescuentoProducto, CondicionNotaCredito).
- Fase 2/3: espejo de Odoo, bandeja de facturación, equivalentes congelados.

Todos heredarán de un modelo base abstracto de la app (UUIDv7 + multi-tenant
``empresa`` + timestamps + *soft delete*), que se introduce en Fase 1 junto a
sus modelos concretos y tests de aislamiento multi-tenant.
"""

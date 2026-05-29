# TD-05: Análisis de Imports Circulares — Omni ERP

**Fecha:** 2026-05-28  
**Estado:** ✅ Sin circulares activos; imports locales usados donde se requiere

---

## Capas de dependencia (de más bajo a más alto)

```
Capa 0 — Infraestructura pura (sin imports inter-app)
  ├── apps.core.uuid          (uuid7 helper)
  ├── apps.core.models        (Empresa, Sucursal, Usuarios, …)
  └── apps.saas.models        (Plan, Suscripcion)

Capa 1 — Datos maestros
  ├── apps.finanzas.models    (Moneda, MetodoPago, Caja, …)
  │   → depende de: core (Empresa via FK, uuid7)
  ├── apps.rrhh.models        (Empleado, LicenciaEmpleado, …)
  │   → depende de: core (Empresa)
  └── apps.inventario.models  (Producto, Stock, …)
      → depende de: core (Empresa, Sucursal)

Capa 2 — Transacciones
  ├── apps.ventas.models      (Pedido, FacturaFiscal, …)
  │   → depende de: core, finanzas (Moneda, TasaCambio — lazily)
  ├── apps.compras.models     (OrdenCompra, FacturaCompra, …)
  │   → depende de: core, finanzas
  └── apps.fiscal.models      (ConfiguracionFiscalEmpresa, TasaIVA, …)
      → depende de: core

Capa 3 — Agregaciones / BI (solo lectura de capas inferiores)
  ├── apps.contabilidad
  ├── apps.cuentas_por_cobrar
  ├── apps.cuentas_por_pagar
  └── apps.costos
```

---

## Imports que usan lazy import para evitar circulares

| Archivo | Línea | Patrón | Razón |
|---|---|---|---|
| `apps/finanzas/models.py` | 1769 | `from apps.ventas.models import Pedido` (dentro de método) | finanzas necesita ventas para Pago; ventas no necesita finanzas a nivel de clase |
| `apps/finanzas/models.py` | 1777 | `from apps.ventas.models import NotaVenta` (dentro de método) | ídem |
| `apps/finanzas/models.py` | 1111, 1128 | `from apps.core.models import Empresa` (dentro de classmethod) | ya importado al nivel de módulo vía FK string; redundante pero seguro |
| `apps/finanzas/models.py` | 299 | `from apps.finanzas.ajustes import crear_ajuste_caja_banco` (dentro de método) | split de responsabilidad dentro del mismo app |

---

## Riesgo actual: BAJO

Los dos imports potencialmente circulares (`finanzas ↔ ventas`) ya están resueltos usando
lazy imports dentro de métodos. No se detectó ningún ciclo activo.

---

## Reglas de dependencia (para nuevos desarrollos)

1. **core** NO debe importar de ningún app de negocio.
2. **finanzas** puede importar de **core**, pero NO de **ventas** a nivel de módulo.
   - Si necesita un modelo de ventas, usar string FK (`"ventas.Pedido"`) o import lazy.
3. **ventas / compras** pueden importar de **core** y **finanzas** (string FK preferido).
4. **contabilidad / costos** solo leen de capas inferiores; nunca circular.
5. **saas** solo depende de **core**.

---

## Verificación automatizada

Para detectar circulares en CI, agregar a `tox.ini` o como step de pre-commit:

```bash
pip install importchecker
importchecker apps/ --transitive | grep CIRCULAR
```

O con `pylint`:
```bash
pylint --load-plugins pylint.extensions.mccabe apps/ | grep "Circular"
```

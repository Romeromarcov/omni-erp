# App `fiscal`

Localización fiscal (capa Venezuela, activable): impuestos (IVA, IGTF), retenciones, contribuciones parafiscales, numeración fiscal correlativa, configuración fiscal por empresa, períodos fiscales y libros legales de ventas/compras (con exportación a PDF). Es la pieza clave de "Venezuela-first" sin hardcodear el núcleo.

**Prefijo API:** `/api/fiscal/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Impuesto` / `ConfiguracionImpuesto` / `ImpuestoEmpresaActiva` | Impuestos y su configuración por empresa. |
| `TasaIVAEmpresa` | Tasas de IVA aplicables por empresa. |
| `Retencion` / `ConfiguracionRetencion` / `RetencionEmpresaActiva` | Retenciones y su configuración. |
| `ContribucionParafiscal` / `ContribucionEmpresaActiva` / `EmpresaContribucionParafiscal` | Contribuciones parafiscales. |
| `ConfiguracionFiscalEmpresa` | Configuración fiscal global por empresa. |
| `NumeroCorrelativo` | Numeración fiscal correlativa. |
| `PeriodoFiscal` | Período fiscal. |

## Endpoints

Recursos REST (CRUD vía router): `configuracion-fiscal/`, `tasas-iva/`.

Rutas y acciones adicionales:

| Ruta | Descripción |
|---|---|
| `GET libro-ventas/` · `libro-compras/` | Libros legales. |
| `GET libro-ventas-pdf/` · `libro-compras-pdf/` | Libros en PDF. |
| `GET periodos-fiscales/` | Períodos fiscales. |
| `POST .../calcular/` | Cálculo de impuestos/retenciones. |

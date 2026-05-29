# App `configuracion_motor`

Motor de configuración del sistema: catálogos y parámetros que el resto de las apps consultan en runtime. Permite parametrizar el comportamiento por empresa sin tocar código.

**Prefijo API:** `/api/configuracion/`

## Modelos

| Modelo | Descripción |
|---|---|
| `TipoDocumento` | Catálogo de tipos de documento del sistema. |
| `ParametroSistema` | Parámetros configurables (clave/valor) por empresa. |
| `CatalogoValor` | Valores de catálogos genéricos reutilizables. |

## Endpoints

Recursos REST (CRUD vía router): `tipos-documento/`, `parametros-sistema/`, `catalogos-valor/`.

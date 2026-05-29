# App `gestion_documental`

Gestión documental: almacenamiento jerárquico de documentos en carpetas, vínculos a entidades de negocio y permisos por documento.

**Prefijo API:** `/api/gestion-documental/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Carpeta` | Carpeta (jerarquía de organización). |
| `Documento` | Documento/archivo con metadatos. |
| `VinculoDocumento` | Vínculo de un documento a una entidad de negocio. |
| `PermisoDocumento` | Permisos de acceso por documento. |

## Endpoints

Recursos REST (CRUD vía router): `carpetas/`, `documentos/`, `vinculos-documento/`, `permisos-documento/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET documentos/{id}/descargar/` | Descargar el archivo del documento. |
| `DELETE documentos/{id}/eliminar-archivo/` | Eliminar el archivo asociado. |
| `POST documentos/...` (subida) | Carga de archivos (acción `detail=False`). |

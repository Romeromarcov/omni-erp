# API de Detección de Dispositivos - Documentación

## Resumen
El sistema de detección de dispositivos permite identificar automáticamente dispositivos de usuario y gestionar cajas físicas asociadas, mejorando la experiencia de login y apertura de sesiones.

## Endpoints

### 1. Login con Detección de Dispositivos
**POST** `/api/auth/login/`

Parámetros opcionales para detección de dispositivos:
- `device_fingerprint`: String único que identifica el dispositivo (requerido para detección)
- `device_user_agent`: User agent del navegador/dispositivo
- `device_ip`: Dirección IP del dispositivo

#### Respuesta Exitosa
```json
{
  "access": "jwt_token_here",
  "refresh": "refresh_token_here",
  "user": { /* datos del usuario */ },
  "dispositivo": {
    "id_dispositivo": "uuid",
    "nombre_dispositivo": "Dispositivo-ABC123",
    "creado": true,
    "accion": "preguntar_caja|abrir_sesion|nada",
    "mensaje": "Mensaje descriptivo de la acción",
    "datos": { /* datos adicionales según la acción */ },
    "sesion_abierta": { /* si se abrió sesión automáticamente */ }
  }
}
```

#### Acciones Posibles
- `"nada"`: No se requiere acción adicional
- `"preguntar_caja"`: Preguntar al usuario si quiere crear caja física
- `"abrir_sesion"`: Se abrió sesión automáticamente en caja existente

### 2. Acciones de Dispositivo
**POST** `/api/core/dispositivos/accion/`

Parámetros requeridos:
- `id_dispositivo`: UUID del dispositivo
- `accion`: Acción a realizar

#### Acciones Disponibles

##### Crear Caja Física
```json
{
  "id_dispositivo": "uuid-del-dispositivo",
  "accion": "crear_caja_fisica",
  "nombre_caja": "Caja Principal",
  "tipo_caja": "VENTA"
}
```

##### No Preguntar Más por Caja
```json
{
  "id_dispositivo": "uuid-del-dispositivo",
  "accion": "no_preguntar_caja"
}
```

##### Abrir Sesión
```json
{
  "id_dispositivo": "uuid-del-dispositivo",
  "accion": "abrir_sesion"
}
```

## Flujo de Trabajo

### Primer Login desde Nuevo Dispositivo
1. Usuario hace login con `device_fingerprint`
2. Sistema detecta dispositivo nuevo
3. Si usuario tiene permisos: pregunta si quiere crear caja física
4. Si no tiene permisos: registra dispositivo sin caja

### Login desde Dispositivo con Caja Asociada
1. Usuario hace login con `device_fingerprint`
2. Sistema reconoce dispositivo y abre sesión automáticamente

### Login desde Dispositivo Registrado sin Caja
1. Usuario hace login con `device_fingerprint`
2. Sistema reconoce dispositivo pero no hace nada adicional

## Generación del Device Fingerprint

El fingerprint debe ser único por dispositivo y consistente. Ejemplo de implementación en JavaScript:

```javascript
function generateDeviceFingerprint() {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  ctx.textBaseline = 'top';
  ctx.font = '14px Arial';
  ctx.fillText('Fingerprint', 2, 2);

  const screenInfo = `${screen.width}x${screen.height}x${screen.colorDepth}`;
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const language = navigator.language;

  const fingerprint = btoa([
    canvas.toDataURL(),
    screenInfo,
    timezone,
    language,
    navigator.platform
  ].join('|')).slice(0, 32);

  return fingerprint;
}
```

## Consideraciones de Seguridad

- El fingerprint se almacena en la base de datos pero no se transmite de vuelta al cliente
- Las acciones requieren autenticación JWT
- Solo el propietario del dispositivo puede realizar acciones sobre él
- Los superusuarios pueden ver todos los dispositivos

## Gestión de Dispositivos

Los dispositivos se pueden gestionar a través del endpoint REST estándar:
- **GET** `/api/core/dispositivos/`: Listar dispositivos
- **POST** `/api/core/dispositivos/`: Crear dispositivo manualmente
- **GET** `/api/core/dispositivos/{id}/`: Detalles de dispositivo
- **PUT/PATCH** `/api/core/dispositivos/{id}/`: Actualizar dispositivo
- **DELETE** `/api/core/dispositivos/{id}/`: Eliminar dispositivo
# Runbook — Arranque del piloto distribuidora (Plan 0)

Pasos **operativos** que ejecuta el founder (no son código). Cubre lo que queda del
[Plan 0](00-piloto-distribuidora.md) una vez cerrada Seguridad Semana-1 (✅) y con el
seed de producción ya disponible (`seed_empresa_inicial`, ✅).

> Orden: **1) sembrar empresa → 2) compilar `.exe` → 3) instalar → 4) smoke test**.

---

## 1. Sembrar la empresa real (tarea 0.4)

En el entorno de **producción** (Railway: `railway run` o consola del servicio backend),
con la contraseña del admin pasada por entorno para que **no quede en el historial del shell**:

```bash
export OMNI_SEED_ADMIN_PASSWORD='<contraseña-fuerte-elegida>'
python manage.py seed_empresa_inicial \
    --nombre-legal "Distribuidora <NOMBRE> C.A." \
    --nombre-comercial "<NOMBRE COMERCIAL>" \
    --rif "J-<########>-#" \
    --email "admin@<dominio>.com" \
    --admin-username "<usuario_admin>" \
    --admin-email "admin@<dominio>.com" \
    --sucursal-nombre "Principal" \
    --moneda-base "VES" \
    --caja-nombre "Caja Principal"
```

- Es **idempotente**: re-ejecutarlo no duplica ni cambia la contraseña de un admin ya creado.
- Si omites `OMNI_SEED_ADMIN_PASSWORD` y `--admin-password`, genera una contraseña y la
  imprime **una sola vez** — guárdala de inmediato.
- El admin de la empresa **NO** es superusuario Omni por defecto. La oficina principal
  (tarea 0.5) consulta en lectura con un usuario con visibilidad o un superusuario Omni;
  para ese caso, siembra ese usuario por separado o usa `--es-superusuario-omni`.
- **No uses `create_initial_data`** en producción: crea `admin/admin123` y está bloqueado
  fuera de DEBUG.

### Cargar datos reales (clientes, productos, inventario, saldos CxC)

Los importadores ya existen (`apps/migracion_datos/management/commands/`). Cada uno corre
primero en *dry-run* y luego con `--confirm`:

```bash
python manage.py importar_clientes          --archivo clientes.csv          --empresa "J-<########>-#"
python manage.py importar_productos         --archivo productos.csv         --empresa "J-<########>-#"
python manage.py importar_inventario_inicial --archivo inventario.csv        --empresa "J-<########>-#"
python manage.py importar_saldos_cxc        --archivo saldos_cxc.csv        --empresa "J-<########>-#"
# añade --confirm a cada uno tras revisar el reporte del dry-run
```

---

## 2. Compilar el `.exe` apuntando a producción (tarea 0.2)

En una máquina **Windows** con Node instalado:

```bash
cd frontend
# La URL del backend de producción (Railway) queda embebida en el build:
set VITE_API_URL=https://<backend-railway>/api   # PowerShell: $env:VITE_API_URL="https://<backend-railway>/api"
npm ci
npm run electron:build
```

Genera en `frontend/release/` el instalador NSIS `OmniERP-*.exe` y el portable.
Config: `frontend/electron-builder.json`, `frontend/electron/main.cjs`.

### Firma de código (tarea 0.3) — DIFERIDA

Para el piloto interno **no se firma**. Windows mostrará un aviso de SmartScreen al instalar:
"Más información → Ejecutar de todas formas". La firma EV Authenticode se aborda en el
[Plan B](02-apps-multiplataforma.md) / [CTF-010](../ctf/CTF-010.md).

---

## 3. Instalar en la máquina de la distribuidora

1. Copia el `.exe` (o portable) a la máquina del local.
2. Instala aceptando el aviso de SmartScreen.
3. Abre la app: debe cargar el login apuntando a la API de producción.
4. Inicia sesión con el admin sembrado en el paso 1.

> ⚠ **Sin offline:** si se cae la red, tras ~5 min de caché la app deja de operar
> (ver [Plan A](01-offline-first.md) / [CTF-008](../ctf/CTF-008.md)). El piloto asume
> internet estable en el local.

---

## 4. Smoke test del ciclo real (tarea 0.6)

Contra el `.exe` instalado, verifica el flujo crítico de extremo a extremo
(R-CODE-9). Marca cada paso:

- [ ] **Login** del admin OK.
- [ ] **Factura fiscal** real: correlativo válido, RIF emisor/receptor, IVA/IGTF discriminado.
- [ ] **Cobro en caja** con pago mixto VES + USD.
- [ ] **CxC**: el saldo del cliente refleja la venta/cobro.
- [ ] **Cierre de caja** con cuadre (probar sobrante/faltante).
- [ ] **Libro de Ventas SENIAT** del período se genera (TXT + PDF).
- [ ] **Oficina principal** (tarea 0.5): un usuario con visibilidad consulta los datos
      de la distribuidora por web en lectura.

Si algo falla, es bug en caliente: arréglalo por PR (gate de cierre) antes de declarar 1.F operativa.

---

## Estado del Plan 0 (resumen)

| Tarea | Estado |
|---|---|
| 0.1 Seguridad Semana-1 | ✅ cerrada en `main` |
| 0.2 Compilar `.exe` | ⬜ ejecutar (paso 2) |
| 0.3 Decisión de firma | ✅ diferida (CTF-010) |
| 0.4 Empresa + usuarios (tooling) | ✅ `seed_empresa_inicial`; ⬜ correr con datos reales |
| 0.5 Seguimiento oficina principal | ✅ sin código nuevo; ⬜ verificar en smoke |
| 0.6 Smoke test | ⬜ ejecutar (paso 4) |

**Métrica de cierre 1.F:** 30 días continuos de operación real sin recaída.

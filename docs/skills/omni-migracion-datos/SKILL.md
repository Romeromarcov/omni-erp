---
name: omni-migracion-datos
description: Use this skill whenever you import real customer data into Omni or write/modify a data-import management command. Triggers include importing clients, products, initial inventory, or CxC balances (sub-fase 1.F — distribuidora en producción), any work under `apps/migracion_datos/`, subclassing `ImportadorBaseCommand`, CSV ingestion with dry-run/`--confirm`, row-by-row validation, or idempotent importers. Apply it whenever the task is loading external/legacy data into the system safely. Do NOT use for Django schema migrations (those are `makemigrations`/`migrate`), normal app logic, or frontend.
---

# Skill: Migración / Importación de Datos Reales (TRACK-1F)

## Cuándo usar esta skill

Cargá esta skill cuando:
- Importás datos reales de un cliente: clientes, productos, inventario inicial, saldos CxC.
- Escribís o modificás un management command de importación en `apps/migracion_datos/`.
- Trabajás con importadores CSV idempotentes con validación fila por fila.

**Relevante ahora:** la sub-fase **1.F (distribuidora en producción)** depende de cargar datos reales. Los importadores ya existen; el trabajo es usarlos/extenderlos bien.

No la cargués para migraciones de schema Django (`makemigrations`/`migrate`), lógica normal de app, ni frontend.

> **Ojo con el vocabulario:** "migración de datos" (esta skill, importar datos de negocio) ≠ "migración Django" (cambios de schema). Son cosas distintas.

## Por qué importa hacerlo bien

Importar datos reales mal es peor que no importarlos: saldos CxC equivocados, productos duplicados o stock inicial incorrecto **rompen la confianza del cliente piloto el primer día**. Por eso los importadores son **idempotentes, validados fila por fila, y dry-run por defecto**.

## La base: `ImportadorBaseCommand`

Vive en `apps/migracion_datos/management/commands/_importador_base.py`. **Todo importador hereda de ella** y solo implementa `procesar_fila`.

La base provee gratis:
- Argumentos `--archivo`, `--empresa`, `--confirm`.
- Resolución defensiva de la empresa (UUID pk, luego `identificador_fiscal`, `nombre_comercial`, `nombre_legal`; error claro si ambiguo).
- Parseo CSV con `csv.DictReader` y `utf-8-sig` (sin pandas).
- **Dry-run por defecto; escritura real solo con `--confirm`.**
- **Todo-o-nada:** si alguna fila falla, se revierte la transacción completa (no se escribe nada).
- Reporte estandarizado: filas OK / filas con error (número de línea + mensaje).
- Helpers de parseo: `requerido`, `opcional`, `a_decimal`.

## Patrón: escribir un importador

```python
# apps/migracion_datos/management/commands/importar_<entidad>.py
from ._importador_base import ImportadorBaseCommand, FilaError


class Command(ImportadorBaseCommand):
    help = "Importa <entidad> desde un CSV."
    nombre_entidad = "<entidad>"      # aparece en los reportes

    def procesar_fila(self, empresa, fila, numero_linea):
        """Procesa UNA fila ya parseada (dict).
        Devuelve "creado" o "actualizado"; lanza FilaError(mensaje) si es inválida.
        Solo se llama en modo --confirm; en dry-run la base usa validar_fila
        (que ejecuta esto dentro de un savepoint y lo revierte).
        """
        codigo = self.requerido(fila, "codigo")            # error si falta
        nombre = self.requerido(fila, "nombre")
        precio = self.a_decimal(fila.get("precio"), "precio")   # Decimal, error si no es número

        # Validación de negocio explícita:
        if precio < 0:
            raise FilaError(f"precio negativo: {precio}")

        # Idempotente: update_or_create por clave natural DENTRO de la empresa
        obj, creado = MiEntidad.objects.update_or_create(
            id_empresa=empresa,
            codigo=codigo,                                  # clave natural por empresa
            defaults={"nombre": nombre, "precio": precio},
        )
        return "creado" if creado else "actualizado"
```

## Las cuatro garantías que NO se rompen

1. **Idempotencia:** correr el importador dos veces con el mismo archivo no duplica datos. Usá `update_or_create` por una **clave natural única por empresa** (código, RIF, etc.), nunca `create` ciego.
2. **Multi-tenant:** todo se crea/busca con `id_empresa=empresa`. La empresa la resuelve la base desde `--empresa`. Nunca importes sin empresa (ver `omni-multi-tenant-isolation`).
3. **Dry-run primero:** corré siempre sin `--confirm` para ver el reporte de validación antes de escribir. La escritura real es `--confirm`.
4. **Dinero en Decimal:** usá `self.a_decimal(...)`, nunca `float()`. Saldos CxC e inventario inicial valorizado son dinero (ver `omni-decimal-money`).

## Flujo de uso

```bash
cd backend

# 1) Dry-run: valida y reporta, no escribe nada
python manage.py importar_clientes --archivo clientes.csv --empresa "Distribuidora XYZ"

# 2) Revisá el reporte: "Filas OK: N/Total", y las líneas con error
#    Corregí el CSV hasta que no haya errores.

# 3) Escritura real (solo cuando el dry-run está limpio)
python manage.py importar_clientes --archivo clientes.csv --empresa <uuid> --confirm
```

> Si una sola fila falla en `--confirm`, **no se escribe nada** (todo-o-nada). El reporte indica qué línea y por qué. Corregí y reintentá.

## Validación fila por fila

Cada fila se valida independientemente y los errores se acumulan con su número de línea (la línea 1 es la cabecera; los datos empiezan en la 2). Lanzá `FilaError(mensaje_legible)` con un mensaje que el operador pueda accionar:

```python
# BIEN — mensaje accionable
raise FilaError(f"RIF inválido: '{rif}'")

# MAL — error opaco
raise ValueError("bad data")
```

Para validaciones de dominio (RIF venezolano, etc.) reusá los validadores existentes (ver `omni-venezuela-fiscal` para RIF).

## Anti-patrones

### Anti-patrón 1: `create` en vez de `update_or_create`
```python
# MAL — reimportar duplica todo
MiEntidad.objects.create(id_empresa=empresa, codigo=codigo, ...)

# BIEN — idempotente por clave natural
MiEntidad.objects.update_or_create(id_empresa=empresa, codigo=codigo, defaults={...})
```

### Anti-patrón 2: escribir sin dry-run
```python
# MAL — correr directo con --confirm en datos reales del cliente
# BIEN — dry-run, revisar el reporte, recién entonces --confirm
```

### Anti-patrón 3: float en saldos/precios
```python
# MAL
precio = float(fila["precio"])
# BIEN
precio = self.a_decimal(fila.get("precio"), "precio")
```

### Anti-patrón 4: importar sin empresa / sin filtrar por empresa
```python
# MAL — MiEntidad.objects.update_or_create(codigo=codigo, ...)  (sin id_empresa)
# BIEN — siempre id_empresa=empresa en create y en lookup
```

### Anti-patrón 5: reinventar el parseo/transacción
```python
# MAL — abrir el CSV, manejar la transacción y el reporte a mano
# BIEN — heredar de ImportadorBaseCommand y solo implementar procesar_fila
```

### Anti-patrón 6: pandas para un CSV simple
```python
# MAL — sumar dependencia pesada; la base usa csv stdlib
# BIEN — usar los helpers de la base (requerido/opcional/a_decimal)
```

## Checklist final

- [ ] El importador hereda de `ImportadorBaseCommand`; solo implementa `procesar_fila`.
- [ ] `procesar_fila` es idempotente (`update_or_create` por clave natural única por empresa).
- [ ] Todo create/lookup usa `id_empresa=empresa`.
- [ ] Montos vía `self.a_decimal`, nunca `float`.
- [ ] Campos requeridos con `self.requerido`; errores con `FilaError` y mensaje accionable.
- [ ] Probado primero en dry-run; el reporte queda limpio antes de `--confirm`.
- [ ] Validaciones de dominio (RIF, etc.) reusan validadores existentes.

## Referencias

- Código: `apps/migracion_datos/management/commands/_importador_base.py` (base), `importar_clientes.py`, `importar_productos.py`, `importar_inventario_inicial.py`, `importar_saldos_cxc.py`.
- Skill: `omni-multi-tenant-isolation`, `omni-decimal-money`, `omni-venezuela-fiscal` (RIF), `omni-testing-pytest`.
- Plan Maestro §5.2 (sub-fase 1.F), TRACK-1F.

## Changelog

### v1.0
- Versión inicial, basada en `apps/migracion_datos/`.

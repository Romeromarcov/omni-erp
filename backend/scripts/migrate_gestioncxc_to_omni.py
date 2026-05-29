"""
Script de migración one-time: GestionCxC (sistema anterior) → Omni CxC

Migra datos históricos de GestionCxC a los modelos de apps.cxc.

Tablas migradas:
  cobranza_gestiones   → cxc.GestionCobranza
  acuerdos_pago        → cxc.AcuerdoPago
  acuerdos_pago_cuotas → cxc.CuotaAcuerdo
  cobranza_plantillas  → cxc.PlantillaCobranza
  tasas_cambio         → finanzas.TasaCambio (históricas)

USO:
    cd backend/
    python scripts/migrate_gestioncxc_to_omni.py \
        --empresa-id <UUID> \
        --source-db <postgresql://user:pass@host/dbname>

    # Dry run (no escribe nada):
    python scripts/migrate_gestioncxc_to_omni.py --empresa-id <UUID> --source-db <DSN> --dry-run

REQUISITOS:
    - psycopg2 (pip install psycopg2-binary)
    - Django settings configuradas (settings_dev o settings_prod)
    - La empresa debe existir en Omni

GARANTÍAS:
    - Idempotente: puede correrse múltiples veces sin duplicados.
    - Transaccional: si falla, revierte todo.
    - Solo migra hacia adelante: no modifica la BD origen.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Asegurar que Django esté inicializado
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")

import django
django.setup()

from django.db import transaction, connections

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_decimal(val, default=Decimal("0")) -> Decimal:
    try:
        return Decimal(str(val)) if val is not None else default
    except InvalidOperation:
        return default


def _safe_str(val, default="") -> str:
    return str(val).strip() if val is not None else default


def _safe_date(val):
    """Convierte varios formatos de fecha a date o None."""
    if val is None:
        return None
    if hasattr(val, "date"):
        return val.date()
    if hasattr(val, "year"):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ── Migración de plantillas ───────────────────────────────────────────────────

def migrar_plantillas(cursor, empresa, dry_run: bool) -> int:
    """Migra plantillas de cobranza."""
    from apps.cxc.models import PlantillaCobranza

    cursor.execute("""
        SELECT id, nombre, canal, asunto, cuerpo, activa
        FROM cobranza_plantillas
        ORDER BY id
    """)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    migrados = 0
    for row in rows:
        rec = dict(zip(cols, row))

        if dry_run:
            logger.info("[DRY-RUN] Plantilla: %s", rec.get("nombre"))
            continue

        _, created = PlantillaCobranza.objects.get_or_create(
            empresa=empresa,
            nombre=_safe_str(rec.get("nombre")),
            canal=_safe_str(rec.get("canal"), "llamada"),
            defaults={
                "asunto": _safe_str(rec.get("asunto")),
                "cuerpo": _safe_str(rec.get("cuerpo")),
                "activa": bool(rec.get("activa", True)),
            },
        )
        if created:
            migrados += 1

    logger.info("Plantillas migradas: %d (dry_run=%s)", migrados, dry_run)
    return migrados


# ── Migración de gestiones ────────────────────────────────────────────────────

def migrar_gestiones(cursor, empresa, dry_run: bool) -> int:
    """Migra gestiones de cobranza."""
    from apps.cxc.models import GestionCobranza

    cursor.execute("""
        SELECT id, cliente_id, cliente_nombre, orden_ref, canal, resultado,
               notas, fecha_gestion, proxima_accion, score
        FROM cobranza_gestiones
        ORDER BY fecha_gestion
    """)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    # Mapeo de canales y resultados
    CANAL_MAP = {
        "whatsapp": "whatsapp", "email": "email", "llamada": "llamada",
        "visita": "visita", "carta": "carta",
        "sms": "whatsapp",  # fallback
    }
    RESULTADO_MAP = {
        "contactado": "contactado", "sin_respuesta": "sin_respuesta",
        "promesa_pago": "promesa_pago", "negativa": "negativa",
        "acuerdo_logrado": "acuerdo_logrado",
        "no_contactado": "sin_respuesta",  # fallback
    }

    migrados = 0
    for row in rows:
        rec = dict(zip(cols, row))
        canal = CANAL_MAP.get(_safe_str(rec.get("canal")).lower(), "llamada")
        resultado = RESULTADO_MAP.get(_safe_str(rec.get("resultado")).lower(), "contactado")

        if dry_run:
            logger.info(
                "[DRY-RUN] Gestión: %s — %s → %s",
                rec.get("cliente_nombre"), canal, resultado,
            )
            continue

        _, created = GestionCobranza.objects.get_or_create(
            empresa=empresa,
            cliente_id=_safe_str(rec.get("cliente_id")),
            canal=canal,
            resultado=resultado,
            fecha_gestion=_safe_date(rec.get("fecha_gestion")) or datetime.today().date(),
            defaults={
                "cliente_nombre": _safe_str(rec.get("cliente_nombre")),
                "orden_ref": _safe_str(rec.get("orden_ref")),
                "notas": _safe_str(rec.get("notas")),
                "proxima_accion": _safe_date(rec.get("proxima_accion")),
                "score": _safe_decimal(rec.get("score")),
            },
        )
        if created:
            migrados += 1

    logger.info("Gestiones migradas: %d (dry_run=%s)", migrados, dry_run)
    return migrados


# ── Migración de acuerdos ─────────────────────────────────────────────────────

def migrar_acuerdos(cursor, empresa, dry_run: bool) -> dict:
    """Migra acuerdos de pago y sus cuotas."""
    from apps.cxc.models import AcuerdoPago, CuotaAcuerdo

    cursor.execute("""
        SELECT id, cliente_id, cliente_nombre, monto_total, periodicidad,
               plazo_total_dias, fecha_inicio, monto_cuota, porcentaje_abono,
               estado, moneda_codigo, observaciones
        FROM acuerdos_pago
        ORDER BY fecha_inicio
    """)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    ESTADO_MAP = {
        "vigente": "vigente", "cumplido": "cumplido",
        "roto": "roto", "cancelado": "cancelado",
        "activo": "vigente", "completado": "cumplido",
    }

    migrados_ac = 0
    migrados_cu = 0
    id_map = {}  # id_gestion_cxc → id_omni

    for row in rows:
        rec = dict(zip(cols, row))
        estado = ESTADO_MAP.get(_safe_str(rec.get("estado")).lower(), "vigente")

        if dry_run:
            logger.info("[DRY-RUN] Acuerdo: %s $%s", rec.get("cliente_nombre"), rec.get("monto_total"))
            continue

        acuerdo, created = AcuerdoPago.objects.get_or_create(
            empresa=empresa,
            cliente_id=_safe_str(rec.get("cliente_id")),
            fecha_inicio=_safe_date(rec.get("fecha_inicio")) or datetime.today().date(),
            monto_total=_safe_decimal(rec.get("monto_total")),
            defaults={
                "cliente_nombre": _safe_str(rec.get("cliente_nombre")),
                "periodicidad": _safe_str(rec.get("periodicidad"), "mensual"),
                "plazo_total_dias": int(rec.get("plazo_total_dias") or 30),
                "monto_cuota": _safe_decimal(rec.get("monto_cuota")) if rec.get("monto_cuota") else None,
                "porcentaje_abono": _safe_decimal(rec.get("porcentaje_abono")) if rec.get("porcentaje_abono") else None,
                "estado": estado,
                "moneda_codigo": _safe_str(rec.get("moneda_codigo"), "USD"),
                "observaciones": _safe_str(rec.get("observaciones")),
            },
        )
        if created:
            migrados_ac += 1
            id_map[rec["id"]] = acuerdo

        # Migrar cuotas del acuerdo
        try:
            cursor.execute("""
                SELECT numero_cuota, fecha_vencimiento, monto, estado, fecha_pago, monto_pagado
                FROM acuerdos_pago_cuotas
                WHERE acuerdo_id = %s
                ORDER BY numero_cuota
            """, [rec["id"]])
            cuota_rows = cursor.fetchall()
            cuota_cols = [d[0] for d in cursor.description]

            CUOTA_ESTADO_MAP = {
                "pendiente": "pendiente", "pagado": "pagado",
                "parcial": "parcial", "vencido": "vencido",
                "paid": "pagado", "pending": "pendiente",
            }

            for cr in cuota_rows:
                crec = dict(zip(cuota_cols, cr))
                cuota_estado = CUOTA_ESTADO_MAP.get(_safe_str(crec.get("estado")).lower(), "pendiente")

                _, cu_created = CuotaAcuerdo.objects.get_or_create(
                    acuerdo=acuerdo,
                    numero_cuota=int(crec.get("numero_cuota") or 1),
                    defaults={
                        "fecha_vencimiento": _safe_date(crec.get("fecha_vencimiento")) or acuerdo.fecha_inicio,
                        "monto": _safe_decimal(crec.get("monto")),
                        "estado": cuota_estado,
                        "fecha_pago": _safe_date(crec.get("fecha_pago")),
                        "monto_pagado": _safe_decimal(crec.get("monto_pagado")),
                    },
                )
                if cu_created:
                    migrados_cu += 1
        except Exception as e:
            logger.warning("No se pudieron migrar cuotas del acuerdo %s: %s", rec["id"], e)

    logger.info("Acuerdos migrados: %d | Cuotas: %d (dry_run=%s)", migrados_ac, migrados_cu, dry_run)
    return {"acuerdos": migrados_ac, "cuotas": migrados_cu}


# ── Migración de tasas históricas ─────────────────────────────────────────────

def migrar_tasas(cursor, empresa, dry_run: bool) -> int:
    """Migra tasas de cambio históricas."""
    from apps.finanzas.models import TasaCambio, Moneda

    try:
        usd = Moneda.objects.get(codigo_iso="USD")
        ves = Moneda.objects.get(codigo_iso="VES")
    except Moneda.DoesNotExist:
        logger.warning("Monedas USD/VES no encontradas — omitiendo migración de tasas")
        return 0

    try:
        cursor.execute("""
            SELECT fecha, tipo, valor
            FROM tasas_cambio
            ORDER BY fecha
        """)
    except Exception:
        logger.info("Tabla tasas_cambio no encontrada en origen — omitiendo")
        return 0

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    TIPO_MAP = {
        "bcv": "OFICIAL_BCV",
        "oficial": "OFICIAL_BCV",
        "binance": "PROMEDIO_MERCADO",
        "p2p": "PROMEDIO_MERCADO",
        "mercado": "PROMEDIO_MERCADO",
    }

    migradas = 0
    for row in rows:
        rec = dict(zip(cols, row))
        tipo_tasa = TIPO_MAP.get(_safe_str(rec.get("tipo")).lower(), "OFICIAL_BCV")
        fecha = _safe_date(rec.get("fecha"))
        if not fecha:
            continue

        if dry_run:
            logger.info("[DRY-RUN] Tasa %s %s = %s", tipo_tasa, fecha, rec.get("valor"))
            continue

        _, created = TasaCambio.objects.get_or_create(
            id_empresa=None,  # tasas BCV son globales
            id_moneda_origen=usd,
            id_moneda_destino=ves,
            tipo_tasa=tipo_tasa,
            fecha_tasa=fecha,
            defaults={
                "valor_tasa": _safe_decimal(rec.get("valor"), Decimal("1")),
                "referencia_externa": "migrate_gestioncxc",
            },
        )
        if created:
            migradas += 1

    logger.info("Tasas migradas: %d (dry_run=%s)", migradas, dry_run)
    return migradas


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migrar GestionCxC a Omni CxC")
    parser.add_argument("--empresa-id", required=True, help="UUID de la empresa destino en Omni")
    parser.add_argument("--source-db", required=True, help="DSN PostgreSQL origen ej: postgresql://user:pass@host/db")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada — solo reporta")
    args = parser.parse_args()

    from apps.core.models import Empresa

    try:
        empresa = Empresa.objects.get(pk=args.empresa_id)
    except Empresa.DoesNotExist:
        logger.error("Empresa %s no encontrada en Omni", args.empresa_id)
        sys.exit(1)

    logger.info("=== Migración GestionCxC → Omni CxC ===")
    logger.info("Empresa: %s | Dry-run: %s", empresa, args.dry_run)
    logger.info("Origen: %s", args.source_db[:30] + "...")

    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 no instalado. Ejecutar: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(args.source_db)
    cursor = conn.cursor()

    try:
        with transaction.atomic():
            totales = {}

            totales["plantillas"] = migrar_plantillas(cursor, empresa, args.dry_run)
            totales["gestiones"] = migrar_gestiones(cursor, empresa, args.dry_run)
            totales["tasas"] = migrar_tasas(cursor, empresa, args.dry_run)
            resultado_ac = migrar_acuerdos(cursor, empresa, args.dry_run)
            totales.update(resultado_ac)

            if args.dry_run:
                logger.info("=== DRY-RUN completado — no se escribió nada ===")
            else:
                logger.info("=== Migración completada ===")

            for k, v in totales.items():
                logger.info("  %s: %s", k, v)

    except Exception as e:
        logger.exception("Error durante la migración: %s", e)
        conn.close()
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()

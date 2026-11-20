"""Row Level Security (RLS) — P0-1 del plan de hardening de seguridad.

Ver ``docs/planes/05-seguridad-hardening.md`` (P0-1) y ``docs/ctf/CTF-012.md``.

Capa de aislamiento multi-tenant **a nivel de PostgreSQL**, como defensa en
profundidad sobre el filtrado a nivel de aplicación (``get_empresas_visible``).
Si un queryset olvidara el filtro por empresa, la base de datos sigue evitando
la fuga cross-tenant.

Modelo de enforcement
---------------------
- GUC ``omni.rls_empresas``: lista CSV de UUIDs de empresas visibles.
- GUC ``omni.rls_bypass``: ``'on'`` => la fila siempre es visible (superusuario
  Omni y contextos de sistema). Cualquier otro valor / ausente => ``'off'``.
- Política por tabla: la fila es visible si ``bypass='on'`` **o** su columna de
  empresa pertenece al conjunto de ``omni.rls_empresas``. Sin contexto fijado la
  expresión evalúa a falso => **0 filas (fail-closed)**.
- ``FORCE ROW LEVEL SECURITY``: necesario porque, mientras el dueño sea dueño de
  las tablas, sin ``FORCE`` el dueño saltaría las políticas. Con el rol
  dedicado ``omni_app`` (no-dueño, ``NOSUPERUSER NOBYPASSRLS``) RLS aplica por
  construcción.

Estado por defecto de las conexiones
------------------------------------
- Cuando ``settings.RLS_ENABLED`` es ``False`` (default de transición mientras
  se despliega el rol ``omni_app``): ``connection_created`` y
  ``apply_system_default()`` fijan ``bypass='on'`` para mantener total
  compatibilidad en migraciones, Celery, comandos y tests existentes.
- Cuando ``settings.RLS_ENABLED`` es ``True``: ``connection_created`` y
  ``apply_system_default()`` fijan **fail-closed por defecto**
  (``omni.rls_bypass='off'``, ``omni.rls_empresas=''``). Todo código que opere
  fuera de ``RLSContextMiddleware`` debe abrir explícitamente
  ``with rls.rls_tenant_context([...]):`` o ``with rls.rls_bypass():``.
"""

from __future__ import annotations

import re
import uuid
from contextlib import contextmanager

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections

# Nombres de los parámetros de sesión (GUC) de PostgreSQL.
GUC_EMPRESAS = "omni.rls_empresas"
GUC_BYPASS = "omni.rls_bypass"

# Nombre uniforme de la política en todas las tablas.
POLICY_NAME = "omni_rls_tenant"

# Identificadores SQL permitidos (tabla / columna). Se validan con whitelist
# porque se interpolan en DDL; nunca provienen de entrada de usuario.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _check_ident(ident: str) -> str:
    if not _IDENT_RE.match(ident):
        raise ValueError(f"Identificador SQL inválido para RLS: {ident!r}")
    return ident


def _predicate(empresa_column: str, *, null_visible: bool = False) -> str:
    col = _check_ident(empresa_column)
    null_clause = f'OR "{col}" IS NULL ' if null_visible else ""
    return (
        f"coalesce(current_setting('{GUC_BYPASS}', true), 'off') = 'on' "
        f"{null_clause}"
        f'OR "{col}"::text = ANY (string_to_array('
        f"coalesce(current_setting('{GUC_EMPRESAS}', true), ''), ','))"
    )


def build_enable_rls_sql(table: str, empresa_column: str = "id_empresa_id", *, null_visible: bool = False) -> str:
    """SQL idempotente para activar RLS forzado y la política en ``table``.

    ``empresa_column`` varía por tabla: ``id_empresa_id`` (FK por defecto de
    Django), ``id_empresa`` (FK con ``db_column``) o ``empresa_id``.

    ``null_visible=True`` es para catálogos compartidos cuya columna de empresa
    es *nullable*: una fila con empresa ``NULL`` es global y visible para todos
    los tenants (semántica que ya aplica el filtrado de aplicación, p. ej.
    ``Q(empresa__isnull=True) | Q(empresa__in=visibles)``). El ``WITH CHECK``
    usa el mismo predicado (simétrico): escribir una fila global sigue
    gobernado por la autorización de aplicación; la defensa de BD bloquea
    escribir filas de *otra* empresa.
    """
    table = _check_ident(table)
    predicate = _predicate(empresa_column, null_visible=null_visible)
    return "\n".join(
        [
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;',  # nosec B608
            f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;',  # nosec B608
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";',  # nosec B608
            f'CREATE POLICY {POLICY_NAME} ON "{table}"'  # nosec B608
            f"\n    USING ({predicate})"
            f"\n    WITH CHECK ({predicate});",
        ]
    )


def build_disable_rls_sql(table: str) -> str:
    """SQL para revertir lo aplicado por :func:`build_enable_rls_sql`."""
    table = _check_ident(table)
    return "\n".join(
        [
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}";',  # nosec B608
            f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;',  # nosec B608
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;',  # nosec B608
        ]
    )


# --- Runtime: fijar el contexto RLS en la conexión ------------------------


def _set_config(cursor, name: str, value: str) -> None:
    # set_config parametrizado evita problemas de quoting e inyección.
    cursor.execute("SELECT set_config(%s, %s, false)", [name, value])


def apply_context(empresa_ids, *, bypass: bool = False, using: str = DEFAULT_DB_ALIAS) -> None:
    """Fija el contexto RLS (empresas visibles + bypass) en la conexión."""
    csv = ",".join(str(e) for e in empresa_ids) if empresa_ids else ""
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on" if bypass else "off")
        _set_config(cursor, GUC_EMPRESAS, csv)


def current_role_bypasses_rls(using: str = DEFAULT_DB_ALIAS) -> bool:
    """True si el rol de conexión salta RLS (``SUPERUSER`` o ``BYPASSRLS``).

    Un superusuario o un rol con ``BYPASSRLS`` ignora las políticas RLS aunque
    estén ``FORCE``; en ese caso el aislamiento no es verificable directamente
    (p. ej. el rol ``postgres`` por defecto en CI). Los tests usan esto para,
    cuando aplica, hacer ``SET ROLE`` a un rol no-privilegiado y poder verificar
    el enforcement. En prod, el blocker documentado es conectar la app con un rol
    dedicado no-dueño y sin estos atributos.
    """
    with connections[using].cursor() as cursor:
        cursor.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        row = cursor.fetchone()
    return bool(row and row[0])


def default_bypass_value() -> str:
    """Retorna ``'off'`` (fail-closed) si ``RLS_ENABLED=True``, o ``'on'`` si ``False``."""
    return "off" if getattr(settings, "RLS_ENABLED", False) else "on"


def apply_system_default_on_cursor(cursor) -> None:
    """Fija los GUC RLS por defecto sobre un cursor ya abierto."""
    _set_config(cursor, GUC_BYPASS, default_bypass_value())
    _set_config(cursor, GUC_EMPRESAS, "")


def apply_system_default(using: str = DEFAULT_DB_ALIAS) -> None:
    """Restaura el estado RLS por defecto de la conexión.

    Con ``RLS_ENABLED=False`` fija ``bypass='on'`` sin empresas (compatibilidad).
    Con ``RLS_ENABLED=True`` fija ``bypass='off'`` sin empresas (fail-closed).
    """
    with connections[using].cursor() as cursor:
        apply_system_default_on_cursor(cursor)


def _get_current_context(using: str = DEFAULT_DB_ALIAS) -> tuple[str, str]:
    """Lee el estado actual ``(omni.rls_bypass, omni.rls_empresas)`` en la conexión."""
    with connections[using].cursor() as cursor:
        cursor.execute(
            "SELECT current_setting(%s, true), current_setting(%s, true)",
            [GUC_BYPASS, GUC_EMPRESAS],
        )
        row = cursor.fetchone()
    prev_bypass = row[0] if row and row[0] is not None else default_bypass_value()
    prev_empresas = row[1] if row and row[1] is not None else ""
    return prev_bypass, prev_empresas


def _restore_context(prev_bypass: str, prev_empresas: str, *, using: str = DEFAULT_DB_ALIAS) -> None:
    """Restaura ambos GUC al estado previo capturado al entrar a un context manager."""
    conn = connections[using]
    if getattr(conn, "needs_rollback", False):
        return
    with conn.cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, prev_bypass)
        _set_config(cursor, GUC_EMPRESAS, prev_empresas)


@contextmanager
def rls_bypass(using: str = DEFAULT_DB_ALIAS):
    """Contexto explícito de sistema con ``bypass='on'`` (Celery, comandos,
    migraciones, resolución de autenticación).

    Preserva el estado GUC previo (``omni.rls_bypass`` y ``omni.rls_empresas``)
    y lo restaura al salir, permitiendo anidamiento seguro con
    :func:`rls_tenant_context`.
    """
    prev_bypass, prev_empresas = _get_current_context(using)
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on")
    try:
        yield
    finally:
        _restore_context(prev_bypass, prev_empresas, using=using)


@contextmanager
def rls_tenant_context(empresa_ids, *, using: str = DEFAULT_DB_ALIAS):
    """Aplica contexto RLS acotado a ``empresa_ids`` (``bypass='off'``).

    Preserva el estado GUC previo (``omni.rls_bypass`` y ``omni.rls_empresas``)
    y lo restaura al salir, permitiendo anidar contextos de tenant y
    :func:`rls_bypass` de forma determinística.
    """
    if isinstance(empresa_ids, (str, bytes, uuid.UUID)):
        raise TypeError("empresa_ids debe ser un iterable de IDs (ej. [empresa_id]), no un escalar.")
    prev_bypass, prev_empresas = _get_current_context(using)
    apply_context(empresa_ids, bypass=False, using=using)
    try:
        yield
    finally:
        _restore_context(prev_bypass, prev_empresas, using=using)


# --- Registro de cobertura RLS (fuente de verdad para tests) ---------------
#
# RLS_TABLES: toda tabla multi-tenant (con FK a core.Empresa) que tiene RLS
# forzado + política ``omni_rls_tenant`` (tabla -> columna empresa). Cubre las
# tres variantes de nombre de columna del esquema. El rollout avanzó por lotes
# (un PR por grupo de apps, ver docs/planes/05-seguridad-hardening.md P0-1);
# el lote 3 (CTF-012) extendió la cobertura a TODAS las tablas tenant.
#
# Los tests (tests_api/test_rls_rollout.py) verifican que este registro
# coincide 1:1 con los modelos Django (FK a Empresa) y con el estado real en
# pg_policies/pg_class, de modo que un modelo tenant nuevo sin RLS rompe CI.
RLS_TABLES = {
    # Lote 1 — piloto inicial.
    "sucursales": "id_empresa",
    "ventas_pedido": "id_empresa_id",
    "ventas_nota_venta": "id_empresa_id",
    "ventas_factura_fiscal": "id_empresa_id",
    "finanzas_transaccion_financiera": "id_empresa_id",
    "cxc_gestioncobranza": "empresa_id",
    "cxc_acuerdopago": "empresa_id",
    # Lote 2 — inventario / compras / crm.
    "inventario_producto": "id_empresa_id",
    "inventario_stock_actual": "id_empresa_id",
    "inventario_movimiento_inventario": "id_empresa_id",
    "inventario_valoracion_inventario": "id_empresa_id",
    "inventario_paso_operacion": "id_empresa_id",
    "inventario_operacion_inventario": "id_empresa_id",
    "compras_orden_compra": "id_empresa_id",
    "compras_recepcion_mercancia": "id_empresa_id",
    "crm_cliente": "id_empresa_id",
    "crm_contacto_cliente": "id_empresa_id",
    "crm_direccion_cliente": "id_empresa_id",
    # crm ligero + connect (Omni Connect S1)
    "crm_pipeline": "id_empresa_id",
    "crm_etapa": "id_empresa_id",
    "crm_lead": "id_empresa_id",
    "connect_perfil": "id_empresa_id",
    "connect_tarjeta": "id_empresa_id",
    "connect_toque": "id_empresa_id",
    # Lote 3 (CTF-012) — resto de tablas tenant, por app.
    # agentes
    "agentes_config_agente": "id_empresa_id",
    "agentes_prediccionagente": "id_empresa_id",
    # almacenes
    "almacenes_almacen": "id_empresa_id",
    "almacenes_stock_ubicacion": "id_empresa_id",
    "almacenes_ubicacion_almacen": "id_empresa_id",
    # auditoria
    "auditoria_logauditoria": "id_empresa_id",
    # banca_electronica
    "banca_electronica_lote_pago": "id_empresa_id",
    # compras
    "compras_factura_compra": "id_empresa_id",
    "compras_requisicion_compra": "id_empresa_id",
    "compras_solicitud_cotizacion": "id_empresa_id",
    # configuracion_motor
    "configuracion_motor_parametro_sistema": "id_empresa_id",
    # contabilidad
    "contabilidad_asiento_contable": "id_empresa_id",
    "contabilidad_diario": "id_empresa_id",
    "contabilidad_mapeo_contable": "id_empresa_id",
    "contabilidad_periodo_contable": "id_empresa_id",
    "contabilidad_plan_cuentas": "id_empresa_id",
    # control_asistencia
    "control_asistencia_horariotrabajo": "id_empresa_id",
    # cxc_lubrikca (subproyecto CxC Lubrikca, ADR-013 — todas con FK empresa)
    "cxc_lubrikca_descuentomarcacategoria": "empresa_id",
    "cxc_lubrikca_descuentobcvcompleto": "empresa_id",
    "cxc_lubrikca_promocionprimeracompra": "empresa_id",
    "cxc_lubrikca_reglarecurrencia": "empresa_id",
    "cxc_lubrikca_feriado": "empresa_id",
    "cxc_lubrikca_metodopago": "empresa_id",
    "cxc_lubrikca_pedidolubrikca": "empresa_id",
    "cxc_lubrikca_lineapedidolubrikca": "empresa_id",
    "cxc_lubrikca_preciolistalubrikca": "empresa_id",
    "cxc_lubrikca_pagolubrikca": "empresa_id",
    "cxc_lubrikca_vinculacion": "empresa_id",
    "cxc_lubrikca_bandejafacturacion": "empresa_id",
    "cxc_lubrikca_configuracionconciliacion": "empresa_id",
    "cxc_lubrikca_conciliacionlubrikca": "empresa_id",
    # activaciones (eventos en puntos de venta) y bots_ingest (ingesta desde Telegram)
    "activaciones_calendario": "id_empresa_id",
    "activaciones_recurso": "id_empresa_id",
    "activaciones_evento": "id_empresa_id",
    "activaciones_uso_recurso": "id_empresa_id",
    "bots_ingest_usuario": "id_empresa_id",
    "bots_ingest_ingesta": "id_empresa_id",
    "bots_ingest_registro": "id_empresa_id",
    "bots_ingest_latido": "id_empresa_id",
    "bots_ingest_bitacora": "id_empresa_id",
    # core
    "core_capability_token": "empresa_id",
    "core_clave_idempotencia": "empresa_id",
    "core_configuracion_flujo_documentos": "id_empresa_id",
    "core_contacto": "id_empresa_id",
    "core_dispositivo": "empresa_id",
    "core_notificacion": "id_empresa_id",
    "departamentos": "id_empresa",
    "registro_auditoria": "id_empresa",
    "roles": "id_empresa",
    "usuarios_empresas": "empresa_id",
    # costos
    "costos_analisis_variacion_costo": "id_empresa_id",
    "costos_costo_estandar_producto": "id_empresa_id",
    "costos_costo_produccion": "id_empresa_id",
    # cuentas_por_cobrar
    "cuentas_por_cobrar_cuentaporcobrar": "empresa_id",
    # cuentas_por_pagar
    "cuentas_por_pagar_cuentaporpagar": "id_empresa_id",
    "cuentas_por_pagar_diferencia_cambiaria": "id_empresa_id",
    # cxc
    "cxc_lotefraccionado": "empresa_id",
    "cxc_plantillacobranza": "empresa_id",
    "cxc_ventafraccionada": "empresa_id",
    # despacho
    "despacho_despacho": "id_empresa_id",
    # finanzas
    "finanzas_asignacion_pago": "id_empresa_id",
    "finanzas_caja_fisica": "empresa_id",
    "finanzas_caja_virtual": "empresa_id",
    "finanzas_cuenta_bancaria_empresa": "id_empresa_id",
    "finanzas_datafono": "id_empresa_id",
    "finanzas_metodo_pago": "empresa_id",
    "finanzas_metodopagoempresaactiva": "empresa_id",
    "finanzas_moneda": "empresa_id",
    "finanzas_monedaempresaactiva": "empresa_id",
    "finanzas_movimiento_caja_banco": "id_empresa_id",
    "finanzas_pago": "id_empresa_id",
    "finanzas_pago_tercero": "id_empresa_id",
    "finanzas_plantilla_maestro_cajas": "empresa_id",
    "finanzas_sesion_caja_fisica": "empresa_id",
    "finanzas_tasacambio": "id_empresa_id",
    # fiscal
    "fiscal_configuracion_empresa": "id_empresa_id",
    "fiscal_configuracionimpuesto": "empresa_id",
    "fiscal_configuracionretencion": "empresa_id",
    "fiscal_contribucionempresaactiva": "empresa_id",
    "fiscal_contribucionparafiscal": "empresa_id",
    "fiscal_empresacontribucionparafiscal": "empresa_id",
    "fiscal_pago_contribucion_parafiscal": "id_empresa_id",
    "fiscal_impuesto": "empresa_id",
    "fiscal_impuestoempresaactiva": "empresa_id",
    "fiscal_numero_correlativo": "id_empresa_id",
    "fiscal_periodo_fiscal": "id_empresa_id",
    "fiscal_retencionempresaactiva": "empresa_id",
    "fiscal_tasa_iva_empresa": "id_empresa_id",
    # gastos
    "gastos_categoriagasto": "id_empresa_id",
    "gastos_gasto": "id_empresa_id",
    "gastos_reembolsogasto": "id_empresa_id",
    # gestion_aprobaciones
    "gestion_aprobaciones_tipo_aprobacion": "id_empresa_id",
    # gestion_documental
    "gestion_documental_carpeta": "id_empresa_id",
    "gestion_documental_documento": "id_empresa_id",
    # integracion_b2b
    "integracion_b2b_configuracionintegracion": "id_empresa_id",
    # integration_hub
    "integration_hub_conectorinstancia": "id_empresa",
    # inventario
    "inventario_categoria_producto": "id_empresa_id",
    "inventario_conversion_unidad_medida": "id_empresa_id",
    "inventario_lote_producto": "id_empresa_id",
    "inventario_regla_reabastecimiento": "id_empresa_id",
    "inventario_requisicion_interna": "id_empresa_id",
    "inventario_stock_consignacion_cliente": "id_empresa_id",
    "inventario_stock_consignacion_proveedor": "id_empresa_id",
    "inventario_unidad_medida": "id_empresa_id",
    # manufactura
    "manufactura_centro_trabajo": "id_empresa_id",
    "manufactura_configuracion": "empresa_id",
    "manufactura_etapa_produccion": "empresa_id",
    "manufactura_listamateriales": "empresa_id",
    "manufactura_operacion_produccion": "id_empresa_id",
    "manufactura_ordenproduccion": "empresa_id",
    "manufactura_rutaproduccion": "empresa_id",
    # migracion_datos
    "migracion_datos_procesomigracion": "id_empresa_id",
    # nomina
    "nomina_concepto_nomina": "id_empresa_id",
    "nomina_periodo_nomina": "id_empresa_id",
    "nomina_proceso_nomina": "id_empresa_id",
    "nomina_proceso_nomina_extrasalarial": "id_empresa_id",
    # notificaciones
    "notificaciones_evento": "id_empresa_id",
    # personalizacion
    "personalizacion_entidad_instancia": "id_empresa_id",
    "personalizacion_estado_personalizado": "id_empresa_id",
    "personalizacion_personalizacionconfig": "id_empresa_id",
    "personalizacion_vista_personalizada": "id_empresa_id",
    # proveedores
    "proveedores_proveedor": "id_empresa_id",
    # rrhh
    "rrhh_beneficio": "id_empresa_id",
    "rrhh_cargo": "empresa_id",
    "rrhh_empleado": "empresa_id",
    "rrhh_tipo_licencia": "id_empresa_id",
    # saas
    "saas_suscripcion": "id_empresa_id",
    # servicio_cliente
    "servicio_cliente_baseconocimientoarticulo": "id_empresa_id",
    "servicio_cliente_categoriaticket": "id_empresa_id",
    "servicio_cliente_feedbackcliente": "id_empresa_id",
    "servicio_cliente_ticket_soporte": "id_empresa_id",
    # tareas (ejecución operativa y proyectos — ADR-015)
    "tareas_area_operativa": "id_empresa_id",
    "tareas_miembro_area": "id_empresa_id",
    "tareas_proyecto": "id_empresa_id",
    "tareas_seccion_proyecto": "id_empresa_id",
    "tareas_plantilla_recurrente": "id_empresa_id",
    "tareas_minuta_reunion": "id_empresa_id",
    "tareas_tarea": "id_empresa_id",
    "tareas_dependencia": "id_empresa_id",
    "tareas_comentario": "id_empresa_id",
    "tareas_configuracion_seguimiento": "id_empresa_id",
    "tareas_registro_alerta": "id_empresa_id",
    # tesoreria
    "tesoreria_conciliacion_bancaria": "id_empresa_id",
    "tesoreria_configuracion_conciliacion_cuenta": "id_empresa_id",
    "tesoreria_decision_preconciliacion_bancaria": "id_empresa_id",
    "tesoreria_extracto_bancario_archivo": "id_empresa_id",
    "tesoreria_movimiento_bancario": "id_empresa_id",
    "tesoreria_operacion_cambio_divisa": "empresa_id",
    "tesoreria_propuesta_conciliacion_bancaria": "id_empresa_id",
    # ventas
    "ventas_cotizacion": "id_empresa_id",
    "ventas_devolucion_venta": "id_empresa_id",
    "ventas_esquema_comision": "id_empresa_id",
    "ventas_comision_venta": "id_empresa_id",
    "ventas_lista_precio": "id_empresa_id",
    "ventas_nota_credito_fiscal": "id_empresa_id",
    "ventas_nota_credito_venta": "id_empresa_id",
}

# Catálogos compartidos: la columna de empresa es *nullable* y una fila con
# empresa NULL es global (visible para todos los tenants). Su política se crea
# con ``null_visible=True``. Debe coincidir con la nullabilidad real del modelo
# (lo verifica tests_api/test_rls_rollout.py).
RLS_SHARED_NULL_TABLES = frozenset(
    {
        "configuracion_motor_parametro_sistema",
        "cuentas_por_cobrar_cuentaporcobrar",
        "finanzas_caja_fisica",
        "finanzas_caja_virtual",
        "finanzas_metodo_pago",
        "finanzas_moneda",
        "finanzas_tasacambio",
        "fiscal_contribucionparafiscal",
        "fiscal_impuesto",
        "roles",
        "rrhh_cargo",
    }
)

# Tablas CON FK a core.Empresa excluidas del rollout, con razón documentada.
# (Las tablas sin columna de empresa — detalles hijos, catálogos globales,
# tablas de Django/Celery — quedan fuera por definición: el aislamiento les
# llega por la FK a su tabla padre, que sí tiene RLS.)
RLS_EXCLUDED_TABLES = {
    "empresas": (
        "Raíz del modelo de tenant: su FK a Empresa es empresa_matriz_id "
        "(grupos matriz/subsidiarias), no una columna de pertenencia. El "
        "middleware necesita leerla para calcular get_empresas_visible y el "
        "alta de empresas (onboarding) inserta filas cuyo id aún no está en "
        "el contexto (WITH CHECK las bloquearía). Política propia en un PR "
        "dedicado si se decide cubrirla."
    ),
    "fiscal_retencion": (
        "Semántica bi-empresa: dos FKs a Empresa (agente_retencion_id y "
        "sujeto_retenido_id) y filas genéricas del sistema (es_generico). "
        "Una política de una sola columna ocultaría la retención a una de "
        "las dos partes; necesita política propia (OR entre ambas columnas) "
        "en un PR dedicado."
    ),
}

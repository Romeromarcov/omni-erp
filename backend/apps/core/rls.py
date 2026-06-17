"""Row Level Security (RLS) — P0-1 del plan de hardening de seguridad.

Ver ``docs/planes/05-seguridad-hardening.md`` (P0-1).

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
- ``FORCE ROW LEVEL SECURITY``: necesario porque la aplicación se conecta con el
  rol *dueño* de las tablas; sin ``FORCE`` el dueño saltaría las políticas.

Estado por defecto de las conexiones
------------------------------------
El signal ``connection_created`` (``apps/core/signals.py``) fija ``bypass='on'``
en **toda** conexión Django nueva. Así las migraciones, Celery, el shell y los
tests operan con acceso total y no se rompen al activar ``FORCE``. El middleware
web (``apps/core/middleware.py``) baja ``bypass`` a ``'off'`` y fija el conjunto
de empresas **solo** para requests HTTP autenticados, que son la superficie
expuesta. Una conexión externa directa (``psql`` con el rol de la app) que no
fije los GUC queda **fail-closed** (no ve filas), lo que es una defensa extra.

El flag ``settings.RLS_ENABLED`` gobierna únicamente si el middleware aplica el
enforcement; el signal de default y las políticas existen siempre para que la
base de datos nunca quede en un estado inconsistente.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

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


def build_enable_rls_sql(
    table: str, empresa_column: str = "id_empresa_id", *, null_visible: bool = False
) -> str:
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
        cursor.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def apply_system_default(using: str = DEFAULT_DB_ALIAS) -> None:
    """Estado por defecto de conexiones no-web: ``bypass='on'``, sin empresas.

    Lo usa el signal ``connection_created`` y el middleware al finalizar cada
    request (para no devolver una conexión "cerrada" a un pool si en el futuro
    se habilita ``CONN_MAX_AGE`` / pgbouncer en *session pooling*).
    """
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on")
        _set_config(cursor, GUC_EMPRESAS, "")


@contextmanager
def rls_bypass(using: str = DEFAULT_DB_ALIAS):
    """Marca explícita de contexto de sistema con bypass (Celery, comandos,
    data migrations). El default de conexión ya es bypass; este helper lo hace
    explícito y reaplica el default al salir."""
    with connections[using].cursor() as cursor:
        _set_config(cursor, GUC_BYPASS, "on")
    try:
        yield
    finally:
        apply_system_default(using)


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
    "compras_orden_compra": "id_empresa_id",
    "compras_recepcion_mercancia": "id_empresa_id",
    "crm_cliente": "id_empresa_id",
    "crm_contacto_cliente": "id_empresa_id",
    "crm_direccion_cliente": "id_empresa_id",
    # Lote 3 (CTF-012) — resto de tablas tenant, por app.
    # agentes
    "agentes_config_agente": "id_empresa_id",
    "agentes_prediccionagente": "id_empresa_id",
    # almacenes
    "almacenes_almacen": "id_empresa_id",
    "almacenes_ubicacion_almacen": "id_empresa_id",
    # auditoria
    "auditoria_logauditoria": "id_empresa_id",
    # banca_electronica
    "banca_electronica_cuentabancariaempresa": "empresa_id",
    # compras
    "compras_factura_compra": "id_empresa_id",
    "compras_requisicion_compra": "id_empresa_id",
    "compras_solicitud_cotizacion": "id_empresa_id",
    # configuracion_motor
    "configuracion_motor_parametro_sistema": "id_empresa_id",
    # contabilidad
    "contabilidad_asiento_contable": "id_empresa_id",
    "contabilidad_mapeo_contable": "id_empresa_id",
    "contabilidad_plan_cuentas": "id_empresa_id",
    # control_asistencia
    "control_asistencia_horariotrabajo": "id_empresa_id",
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
    # cxc
    "cxc_lotefraccionado": "empresa_id",
    "cxc_plantillacobranza": "empresa_id",
    "cxc_ventafraccionada": "empresa_id",
    # despacho
    "despacho_despacho": "id_empresa_id",
    # finanzas
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
    # tesoreria
    "tesoreria_conciliacion_bancaria": "id_empresa_id",
    "tesoreria_movimiento_bancario": "id_empresa_id",
    "tesoreria_operacion_cambio_divisa": "empresa_id",
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

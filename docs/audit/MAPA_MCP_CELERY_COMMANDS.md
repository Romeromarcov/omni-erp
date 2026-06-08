# Mapa MCP / Celery / Commands (A1 — generado por `manage.py mapa_superficie`)

## Herramientas MCP

| Tool | Módulo |
|---|---|
| `omni_buscar_cliente` | apps.core.mcp_server |
| `omni_buscar_contacto` | apps.core.mcp_server |
| `omni_crear_pedido` | apps.core.mcp_server |
| `omni_cxc_get_acuerdos_vigentes` | apps.core.mcp_server |
| `omni_cxc_get_aging_summary` | apps.core.mcp_server |
| `omni_cxc_get_cartera_vencida` | apps.core.mcp_server |
| `omni_cxc_get_tasa_cambio_hoy` | apps.core.mcp_server |
| `omni_get_clientes` | apps.core.mcp_server |
| `omni_get_correlativo_fiscal` | apps.core.mcp_server |
| `omni_get_cxc_aging` | apps.core.mcp_server |
| `omni_get_empresas` | apps.core.mcp_server |
| `omni_get_pedidos` | apps.core.mcp_server |
| `omni_get_saldo_cliente` | apps.core.mcp_server |
| `omni_get_stock_producto` | apps.core.mcp_server |
| `omni_get_ventas_resumen` | apps.core.mcp_server |
| `omni_ping` | apps.core.mcp_server |
| `omni_registrar_movimiento_inventario` | apps.core.mcp_server |

_Total tools MCP: 17_

## Tareas Celery

| Tarea | Módulo |
|---|---|
| `agentes.generar_sugerencias_diarias` | apps.agentes.tasks |
| `auditoria.registrar_evento` | apps.auditoria.tasks |
| `config.celery.debug_task` | config.celery |
| `core.log_evento` | apps.core.tasks |
| `core.ping` | apps.core.tasks |
| `gestion_documental.eliminar_archivo_s3` | apps.gestion_documental.tasks |
| `gestion_documental.limpiar_archivos_huerfanos` | apps.gestion_documental.tasks |
| `integration_hub.ejecutar_job_sincronizacion` | apps.integration_hub.tasks |
| `integration_hub.limpiar_logs_antiguos` | apps.integration_hub.tasks |
| `integration_hub.sync_automatico_todos` | apps.integration_hub.tasks |
| `integration_hub.sync_cartera_odoo` | apps.integration_hub.tasks |
| `integration_hub.sync_tasas_ve` | apps.integration_hub.tasks |
| `notificaciones.enviar_notificacion_email` | apps.notificaciones.tasks |

_Total tareas Celery: 13_

## Management commands

| Comando | App |
|---|---|
| `consumir_eventos` | apps.eventos |
| `create_initial_data` | apps.core |
| `importar_clientes` | apps.migracion_datos |
| `importar_inventario_inicial` | apps.migracion_datos |
| `importar_productos` | apps.migracion_datos |
| `importar_saldos_cxc` | apps.migracion_datos |
| `load_test_data` | apps.core |
| `mapa_superficie` | apps.core |
| `migrar_contactos` | apps.core |
| `run_mcp_server` | apps.core |
| `seed_empresa_inicial` | apps.core |

_Total commands: 11_

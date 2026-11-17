# ADR-015: Omni Tareas — Ejecución operativa y proyectos nativos (reemplazo de Asana)

**Estado:** Aceptado
**Fecha:** 2026-11-16
**Autor:** Marco Romero + Agentes de IA co-desarrolladores
**Categoría:** Producto / arquitectura de módulos AI-Native
**Relacionado con:** ADR-002 (modular), ADR-003 (MCP), ADR-004 (agentes), ADR-011 (servicios hermanos / bots), ADR-013 (CxC Lubrikca)

---

## Contexto

La operación diaria del equipo (seguimiento de tareas, proyectos Kanban personales y por área,
tareas recurrentes, minutas con IA y escalación automática de compromisos vencidos) dependía de
Asana externo operado desde `lubrikca-bots/bots/asana` más un panel web separado
(`web/asana_dashboard.py`) y almacenamiento suelto en `kv_store`.

Ese esquema presentaba cuatro limitaciones estructurales:
1. **Silo desconectado del ERP:** una tarea no podía vincularse de forma nativa a una diferencia de
   pre-conciliación bancaria, una factura vencida de CxC, un pedido retenido o un evento de
   activación.
2. **Duplicación de catálogos y gobierno:** mantenía listas paralelas de áreas, miembros, horarios
   y contraseñas fuera de `core.Empresa`, `core.Departamento`, `core.Usuarios` y `bots_ingest`.
3. **Dependencia externa innecesaria:** ataba flujos internos a cuotas, GIDs y webhooks de Asana.
4. **Fricción para agentes de IA:** las capacidades de ejecución del equipo no estaban expuestas en
   el servidor MCP unificado de Omni.

## Decisiones

1. **Módulo nativo transversal `apps/tareas` dentro de Omni ERP.**
   Construido sobre `OmniBaseModel`, PK `uuid7` monótono (R-CODE-5), aislamiento multi-tenant por
   `id_empresa` en aplicación y PostgreSQL `FORCE ROW LEVEL SECURITY` (R-CODE-1).
2. **Cero duplicación con el núcleo:**
   - Las áreas operativas (`AreaOperativa`) enlazan opcionalmente con `core.Departamento` y usan
     `core.Usuarios` para líderes y miembros (`MiembroAreaOperativa`).
   - Los adjuntos de minutas o tareas reutilizan `gestion_documental.Documento` / `VinculoDocumento`.
   - Las alertas in-app emiten `core.Notificacion` y las entregas externas se gobiernan desde
     `notificaciones` y el canal de bots (`bots_ingest`, código estándar `"tareas"`).
3. **Vínculo polimórfico ligero y desacoplado con todo el ERP:**
   `Tarea` incluye `entidad_tipo` (p. ej. `ventas.Pedido`, `tesoreria.PropuestaConciliacionBancaria`,
   `cxc_lubrikca.PedidoLubrikca`, `activaciones.EventoActivacion`) + `entidad_id` (`UUID`, indexado
   por empresa). Ningún módulo del core depende de `apps/tareas`; cualquier flujo puede adjuntar o
   consultar tareas operativas sin acoplamiento circular.
4. **Motor determinístico de recordatorios, recurrencia y escalación en el backend:**
   Se porta y tipa la lógica probada en producción (`escalation.py` v4.2):
   - Ventanas dinámicas por plazo total (`>=30d`, `>=14d`, `>=7d`, `>=2d`, `1d`) y regla especial
     de viernes previo para vencimientos en lunes.
   - Recurrencias (`INTRADIA`, `DIARIA`, `SEMANAL`, `QUINCENAL`, `MENSUAL`) idempotentes.
   - Escalación gradual de vencidas (`tarde 0d` → `mañana 1d` → `24h` → `48h` → `72h` con bloqueo
     automático `bloqueada_por_escalacion=True`) auditada en `RegistroAlertaTarea` para garantizar
     envío exactamente una vez por hito.
5. **AI-Native y API-First (`REST + CapabilityToken + MCP`):**
   - Flujo estructurado de minutas (`MinutaReunion`: borrador extraído/enriquecido con inferencia
     por nombre o área → revisión humana → confirmación atómica de lote de `Tarea`).
   - Endpoints `/api/tareas/` aceptan autenticación humana (`JWT`/`Session`) y máquina-a-máquina
     (`CapabilityToken` con scopes `tareas:read` y `tareas:write`) para que `lubrikca-bots` opere
     contra la misma puerta sin cuentas genéricas ni `asana_dashboard.py`.
   - Herramientas MCP autodiscoverables en `apps/tareas/mcp.py`.

## Consecuencias

- **Integración progresiva sin impacto a producción:** `CxC_Lubrikca` continúa operando sin cambios
  mientras se valida `apps/tareas` en staging (`develop`), luego se construye su UI en Omni y se
  redirige el 5.º bot de `lubrikca-bots` de Asana API a `/api/tareas/` antes de apagar Asana.
- **Trazabilidad multi-tenant completa:** todas las tablas de `apps/tareas` registran políticas RLS
  en `apps/core/rls.py` y validan pertenencia al mismo `id_empresa` en relaciones cruzadas.

# ADR-014: Omni Connect (tarjetas NFC + CRM ligero) como módulo dentro de Omni

**Estado:** Aceptado
**Fecha:** 2026-11-13
**Autor:** Responsable del proyecto
**Categoría:** Producto / arquitectura de módulos
**Relacionado con:** ADR-002 (wedge), ADR-003 (Integration Hub), ADR-004 (agentes), ADR-009 (cxc)

---

## Contexto

Omni Connect convierte una tarjeta o pulsera NFC en el canal de captura de clientes de
Omni ERP: cada toque abre un perfil público, el visitante intercambia su contacto y se crea un
**lead** en un CRM ligero; el lead ganado se vuelve **cliente facturable** (IVA/IGTF ya
resueltos) y se sincroniza con Odoo u otros CRM cuando el cliente ya tiene uno. Es el *wedge* de
entrada (tarjeta de pago único) hacia la suscripción modular de Omni (ADR-002). El primer piloto es
Lubrikca, con Odoo como sistema existente.

Había cuatro decisiones abiertas que bloqueaban el backlog (S1 en adelante).

## Decisiones

1. **Módulo dentro del repo de Omni, no paquete aparte.** Nueva app Django `apps/connect`
   (perfil, tarjeta, toque). Reutiliza multi-tenant (`id_empresa` + RLS), autenticación, planes
   (`saas`) y fiscal sin trabajo extra.
2. **El CRM ligero amplía `apps/crm`**, que hasta ahora solo tenía `Cliente`, `ContactoCliente` y
   `DireccionCliente`. Se agregan `Pipeline`, `Etapa` y `Lead` (S1); `Actividad` llega en S4.
   El `Cliente` existente hace de `partner` facturable: la conversión del lead (S6) crea un
   `Cliente`, no una entidad paralela.
3. **El lead apunta a `core.Contacto`** (identidad unificada, patrón strangler fig). **No** se crean
   `crm_contact` ni `crm_company` nuevos: duplicarían la entidad que el repo está consolidando.
   El vínculo es nulo hasta que la deduplicación (S5) resuelve el lead a un contacto.
4. **Integraciones sobre el Integration Hub existente** (ADR-003): no se crea una capa nueva. S7
   agrega un outbox por evento sobre `ConectorInstancia` y S9 un `push_lead` hacia `crm.lead` de
   Odoo reutilizando `OdooClient`. Los agentes (S12) se registran en `agentes.ConfigAgente` con el
   mismo `NivelAutonomia`; ninguna escritura externa ni envío a un lead sin aprobación humana
   (`gestion_aprobaciones`) en la v1.

## Consecuencias

- **S1 (este cambio)** entrega solo esquema: 3 tablas en `connect`, 3 en `crm`, todas con RLS
  registrada en `rls.RLS_TABLES`, sin API ni UI. Cada FK cross-entity valida en `clean()` que
  pertenezca a la misma empresa.
- **Unicidad global deliberada:** `Perfil.slug` y `Tarjeta.uid_chip` son únicos en toda la base
  (la URL pública corta no lleva tenant; el chip es un objeto físico). Efecto colateral aceptado:
  un tenant puede deducir que un slug o UID ya existe al fallar su alta, sin ver datos del otro.
- **Consentimiento a nivel de BD:** un lead capturado por la vía pública (NFC/QR/enlace) exige
  `consentimiento_aceptado` con fecha y texto aceptado (`CheckConstraint`). La IP del visitante
  nunca se guarda en claro (`Toque.ip_hash`).
- **Odoo de Lubrikca:** el conector actual hace `push_contacto` hacia `res.partner`, que puede
  disparar la lógica fiscal custom (`l10n_ve_full`). Connect solo escribe `crm.lead`.

## Requisitos para las siguientes historias

- **S2 (perfil público):** un request anónimo es fail-closed bajo RLS. Resolver el slug dentro de
  `rls.rls_bypass()` acotado a esa consulta, proyectando solo campos públicos, y servir solo
  tarjetas en estado `ACTIVA` (una `PERDIDA` o `DESACTIVADA` conserva su perfil por historial).
  `Perfil.botones` ya se valida con allowlist (tipos, `http(s)`, teléfonos, correo); la vista debe
  además escapar todo valor al renderizarlo.
- **S2/S3/S6 (servicios que crean registros):** deben llamar `full_clean()`. Las validaciones
  cross-tenant de FKs viven en `clean()` (RLS solo valida la empresa de la fila propia) y
  `objects.create()` no las ejecuta.
- **Unicidad:** `slug`, `uid_chip` y un perfil por usuario son globales y no se liberan al
  desactivar (reasignar un slug impreso en una tarjeta física sería un riesgo). Nombres de
  pipeline y etapa son únicos solo entre registros activos; `Etapa.orden` no es único para
  permitir reordenar el kanban.
- **`Toque`:** tabla de alto volumen sin política de retención aún; definirla en S10 (analíticas).

## Pendiente (no bloquea S1–S6)

- Marca y dominio propios para el producto, o bajo la marca Omni.
- Pasarela de cobro de la tarjeta (Zelle, pago móvil, USDT) y quién factura.
- Perfil digital propio vs. reventa white-label en la fase 0 para validar demanda.
- Costo real por unidad y plazo de importación del hardware (define margen y precio del plan Individual).

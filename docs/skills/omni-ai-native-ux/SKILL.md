---
name: omni-ai-native-ux
description: Use this skill when building or modifying AI-native UX in the Omni frontend — the conversational assistant, agent suggestions, streaming responses, or undo/reversibility affordances. Triggers include "agrega el asistente a X", "muestra sugerencias del agente", "stream de la respuesta IA", "el usuario debe poder deshacer Y", working with AssistantDrawer/AssistantContext, SugerenciasWidget, streamSSE, or surfacing agent output in the UI. Do NOT use for plain CRUD UI with no AI involvement.
---

# Skill: UX AI-Nativa en el Frontend de Omni

## Cuándo usar esta skill

Omni es un ERP **AI-nativo**: los agentes no son un add-on, son parte del
producto. Cargá esta skill cuando la UI:
- Muestra el **asistente conversacional** (drawer global) o lo invoca con contexto.
- Surfacea **sugerencias de un agente** que el humano acepta/rechaza.
- Consume respuestas en **streaming** (SSE).
- Ofrece **deshacer** una acción (propia o de un agente).

## Principio rector: el agente propone, el humano dispone

Del plan maestro (§3.6, niveles de autonomía):

> **Sugerencia:** el agente propone, el humano acepta/rechaza en UI.

Y R-PROD-4:

> **Reversibilidad por defecto:** el usuario deshace cualquier acción (suya o de
> un agente) en un plazo configurable (default 30 días). Co-requisito del agentic.

Implicaciones de UX que debés respetar:
- Una acción de agente **nunca** se aplica de forma irreversible y silenciosa.
- Toda sugerencia muestra **qué propone, por qué, y botones aceptar/rechazar**.
- Toda acción consecuente ofrece **deshacer** (o deja claro el plazo/anulación).
- Distinguí visualmente lo que **hizo/propone la IA** de lo que hizo el humano.

## El Asistente conversacional

Componentes existentes:
- **`contexts/AssistantContext.tsx`** — `AssistantProvider` (montado en
  `AppLayout`) + hook `useAssistant()` → `{ open, setOpen, chat }`.
- **`components/assistant/AssistantDrawer.tsx`** — drawer lateral derecho con
  historial, sugerencias iniciales, input multiline (Enter envía, Shift+Enter
  nueva línea), botón detener/streaming, nueva conversación.
- **`hooks/useAssistantChat.ts`** — estado del chat (`messages`, `streaming`,
  `error`, `send`, `stop`, `reset`).
- **`components/assistant/Markdown.tsx`** — render de las respuestas (react-markdown
  + remark-gfm). Las respuestas del asistente se muestran como Markdown; los
  mensajes del usuario como texto plano.

### Abrir el asistente con contexto

Para invocar el asistente desde una pantalla concreta:

```tsx
import { useAssistant } from '../contexts/AssistantContext';

const { setOpen, chat } = useAssistant();
// abrir y (opcionalmente) sembrar una pregunta contextual
setOpen(true);
chat.send(`Explícame esta factura ${id}`);
```

No crees un segundo drawer ni otro chat: reusá el provider global.

## Streaming (SSE)

Las respuestas del asistente llegan en streaming vía `streamSSE` de
`services/api.ts` (mismo pipeline de auth/refresh/timeout, 90 s):

```ts
import { streamSSE } from '../services/api';

await streamSSE('/agentes/asistente/chat/', (evt) => {
  if (evt.text) appendToLastMessage(evt.text);
  if (evt.error) setError(evt.error);
}, { method: 'POST', body: JSON.stringify({ messages }) });
// El sentinel `data: [DONE]` cierra el stream.
```

UX de streaming:
- Mostrá un cursor/indicador mientras `streaming` es true (el drawer usa `▋`).
- Ofrecé **detener** (`stop`) durante el streaming.
- Deshabilitá el envío mientras hay un stream activo.
- Mensajes parciales se completan token a token; no bloquees el scroll.

## Sugerencias del agente (`SugerenciasWidget`)

`components/SugerenciasWidget.tsx` es el patrón para surfacing de sugerencias
diarias/contextuales (p. ej. cobranza, reorden). Al construir UI de sugerencias:

- Cada tarjeta de sugerencia muestra: **acción propuesta**, **justificación**
  (por qué el agente la sugiere), **confianza/origen** si aplica, y acciones
  **Aceptar / Rechazar / Posponer**.
- Aceptar dispara la acción real (mutación); rechazar registra el feedback (útil
  para la eval suite del agente).
- Estado de modo **sombra vs sugerencia vs autónomo**: hoy los agentes operan en
  sombra/sugerencia (M9). La UI no debe ejecutar acciones autónomas sin que el
  modo lo habilite explícitamente.

## Reversibilidad (deshacer)

- Acciones destructivas o consecuentes → `useConfirm()` antes (ver
  `omni-frontend-forms`), y/o un **snackbar con acción "Deshacer"** después.
- En entidades de negocio el "borrado" es **soft delete / anulación** (R-CODE-6);
  la UI debe ofrecer "Anular" y permitir reactivar dentro del plazo, no un
  delete físico.
- Acciones de agente: deben quedar trazables y reversibles igual que las humanas.

## Errores comunes a evitar

### Error 1: Aplicar una acción de agente sin confirmación ni undo
**Mal:** el agente "ya lo hizo" sin que el humano pueda revisar/revertir.
**Bien:** proponer → aceptar/rechazar → deshacer disponible.

### Error 2: No diferenciar IA de humano
El usuario no sabe qué cambió la IA. Marcá visualmente (icono `AutoAwesome`,
color/badge) el origen agente.

### Error 3: Reinventar el chat
Otro drawer/otro estado de chat. Reusá `AssistantProvider` + `useAssistant`.

### Error 4: Bloquear la UI durante el streaming
Congelar la pantalla. El stream es incremental y cancelable; mantené la UI viva.

### Error 5: Render inseguro de Markdown
Mostrar HTML crudo del modelo. Usá el componente `Markdown` (sanitiza/controla
el render); no `dangerouslySetInnerHTML`.

### Error 6: Tragar errores del stream
Si `evt.error` o el SSE corta, mostralo (el drawer ya tiene `error`).

## Checklist antes de cerrar

- [ ] Sugerencias del agente con justificación + Aceptar/Rechazar.
- [ ] Acciones consecuentes con confirmación previa y/o deshacer.
- [ ] Origen IA distinguible visualmente del origen humano.
- [ ] Chat reusa `AssistantProvider`/`useAssistant`, no un drawer nuevo.
- [ ] Streaming con indicador, botón detener y envío deshabilitado.
- [ ] Respuestas del modelo vía componente `Markdown` (sin HTML crudo).
- [ ] Errores de stream/sugerencia visibles al usuario.
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `contexts/AssistantContext.tsx`, `components/assistant/AssistantDrawer.tsx`,
  `components/assistant/Markdown.tsx`, `hooks/useAssistantChat.ts`,
  `components/SugerenciasWidget.tsx`, `services/api.ts` (`streamSSE`).
- Skills: `omni-frontend-page`, `omni-frontend-forms`, `omni-design-system`.
- Plan maestro §3.6 (niveles de autonomía), R-PROD-4 (reversibilidad), R-CODE-6.
- Memoria: [[project_fabrica_agentes]].

## Changelog

### v1.0 — 2026-06-03
- Versión inicial.

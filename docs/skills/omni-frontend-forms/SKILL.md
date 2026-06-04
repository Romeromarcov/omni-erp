---
name: omni-frontend-forms
description: Use this skill whenever you build or modify a form in the Omni frontend — any create/edit screen, input validation, or submit flow under `frontend/src/`. Triggers include "crea el formulario de X", "agrega validación a Y", "el form de Z debe...", working with react-hook-form, zod schemas in `schemas/`, Controller/register, form-level error handling, or replacing native alert()/confirm(). This is the active workstream (branch `frontend-forms-reskin`). Do NOT use for read-only pages, listings, or pure styling.
---

# Skill: Formularios del Frontend de Omni (react-hook-form + zod)

## Cuándo usar esta skill

Cargá esta skill para **cualquier formulario**: alta, edición, filtros complejos,
modales con inputs. Es el patrón obligatorio del frontend (FE-CRIT-1 migró todos
los forms de venta a react-hook-form; la rama actual `frontend-forms-reskin`
continúa ese trabajo).

Stack: **react-hook-form** + **zod** (vía `@hookform/resolvers/zod`) + **MUI**
para los inputs + **FeedbackContext** para snackbars/confirm.

## Anatomía canónica de un formulario

```tsx
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, MenuItem, Stack, TextField, FormControlLabel, Checkbox } from '@mui/material';
import { post } from '../../../services/api';
import { monedaSchema, type MonedaInput } from '../../../schemas/finanzas.schemas';
import { finanzasKeys } from '../../../lib/queryKeys';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import PageLayout from '../../../components/PageLayout';

const defaultValues: MonedaInput = { tipo_moneda: 'fiat', codigo_iso: '', nombre: '', simbolo: '', decimales: 2, activo: true };

export default function MonedaFormPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const { register, control, handleSubmit, watch, formState: { errors } } =
    useForm<MonedaInput>({ resolver: zodResolver(monedaSchema), mode: 'onBlur', defaultValues });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => post('/finanzas/monedas/', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: finanzasKeys.monedas.all() });
      snackbar.success('Moneda creada correctamente.');
      navigate('/finanzas/monedas');
    },
    onError: () => snackbar.error('No se pudo crear la moneda.'),
  });
  const saving = createMutation.isPending;

  const onSubmit = (values: MonedaInput) => {
    createMutation.mutate({ ...values, fecha_cierre_estimada: values.fecha_cierre_estimada || null });
  };

  return (
    <PageLayout maxWidth={480}>
      <Typography variant="h5" mb={3}>Nueva Moneda</Typography>
      <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
        <Stack spacing={2}>
          {/* select → Controller (valor controlado) */}
          <Controller name="tipo_moneda" control={control} render={({ field }) => (
            <TextField select label="Tipo de Moneda" {...field}
              error={!!errors.tipo_moneda} helperText={errors.tipo_moneda?.message} disabled={saving} fullWidth>
              <MenuItem value="fiat">Fiat</MenuItem>
              <MenuItem value="crypto">Cripto</MenuItem>
              <MenuItem value="otro">Otro</MenuItem>
            </TextField>
          )} />

          {/* text → register */}
          <TextField label="Código ISO" {...register('codigo_iso')}
            error={!!errors.codigo_iso} helperText={errors.codigo_iso?.message} disabled={saving} fullWidth />

          {/* boolean → Controller + Checkbox */}
          <Controller name="activo" control={control} render={({ field }) => (
            <FormControlLabel label="Activo"
              control={<Checkbox checked={!!field.value} onChange={(e) => field.onChange(e.target.checked)} disabled={saving} />} />
          )} />

          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/finanzas/monedas')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={saving}>{saving ? 'Guardando…' : 'Crear'}</Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
}
```

## Reglas del patrón

1. **`mode: 'onBlur'`** — validación al salir del campo (consistente con todo el
   código existente). No `onChange` (ruidoso) salvo necesidad puntual.
2. **`register` para inputs de texto/número simples**; **`Controller` para
   componentes controlados** (selects `TextField select`, `Checkbox`, `Switch`,
   date pickers, autocompletes, campos custom).
3. **Errores por campo:** `error={!!errors.campo}` +
   `helperText={errors.campo?.message}`. El mensaje viene del schema zod.
4. **Errores de envío (servidor):** `<Alert severity="error">` arriba del form, o
   `snackbar.error(...)`. No tragues el error en silencio.
5. **`disabled={saving}`** en todos los inputs y el botón mientras la mutación
   está `isPending`. Botón muestra "Guardando…".
6. **Submit:** `handleSubmit(onSubmit)` — RHF solo llama `onSubmit` si la
   validación zod pasa.

## Schemas zod

Viven en `frontend/src/schemas/<dominio>.schemas.ts` (auth, compras, core,
finanzas, fiscal, ventas). Convenciones:

```ts
import { z } from 'zod';

export const monedaSchema = z.object({
  tipo_moneda: z.enum(['fiat', 'crypto', 'otro'], { errorMap: () => ({ message: 'El tipo de moneda no es válido' }) }),
  codigo_iso: z.string().min(2, 'El código ISO debe tener al menos 2 caracteres').max(5, '...'),
  decimales: z.coerce.number({ invalid_type_error: 'Los decimales deben ser un número' }).int('...').min(0).max(8),
  activo: z.boolean(),
  fecha_cierre_estimada: z.string().optional().refine((v) => !v || /^\d{4}-\d{2}-\d{2}$/.test(v), { message: '...' }),
});
export type MonedaInput = z.infer<typeof monedaSchema>;
```

- **Mensajes de error en español**, concretos y accionables.
- **`z.coerce.number()`** para inputs numéricos (el `<input>` da string).
- **`type XInput = z.infer<typeof xSchema>`** — una sola fuente de verdad para el
  tipo del form. Pasalo a `useForm<XInput>` y a `defaultValues`.
- **Montos como `string`** validados con `.refine(v => Number(v) > 0)`, NO como
  `number` — la aritmética de dinero usa decimal.js (ver `omni-money-ui`).
- Campos opcionales del backend → `.optional()`; convertí `''` a `null` en el
  payload del submit si el backend espera null.

## Feedback: nunca `alert()` / `confirm()` nativos

Usá el **FeedbackContext** (`contexts/feedbackTypes.ts`), montado globalmente por
`FeedbackProvider`:

```tsx
import { useSnackbar, useConfirm } from '../contexts/feedbackTypes';

const snackbar = useSnackbar();   // .success / .error / .info / .warning / .notify
const confirm  = useConfirm();    // Promise<boolean>

snackbar.success('Guardado correctamente.');

const ok = await confirm({ title: 'Anular documento', message: '¿Seguro? Esta acción no se puede deshacer.', destructive: true });
if (!ok) return;
```

`window.alert`, `window.confirm` y `console.log` de debug están **prohibidos**
(la skill `omni-pr-discipline` los detecta y bloquea el PR).

## Formularios complejos (documentos de venta)

Para Cotización/Pedido/NotaVenta/FacturaFiscal existe el hook base
`hooks/useDocumentoVentaBase.ts`: arma `useForm` tipado por el schema del
documento + `useFieldArray` para `detalles`, y centraliza el estado asíncrono
compartido (productos, vendedores, sesión de caja, empresas, sucursales,
clientes similares) vía TanStack Query. **Si tu form es un documento de venta,
extendé ese hook; no dupliques la carga de catálogos.** Estado auxiliar de UI
(staging de línea, `clienteManual`, `descuentoGeneral`, `pagos`) se mantiene como
`useState` local — no son campos directos del form.

## Detección de duplicados (UX de calidad de datos)

Antes de crear entidades sensibles (cliente, moneda, producto) el código usa
fuzzy matching (`utils/fuzzyDuplicate.ts`, `buscarClientesSimilares`) para avisar
"ya existe algo similar". Reusá ese patrón en altas donde un duplicado sea costoso.

## Errores comunes a evitar

### Error 1: Estado de form a mano con `useState`
**Mal:** un `useState` por campo + validación manual en `onSubmit`.
**Bien:** `useForm` + zod. Menos bugs, validación declarativa.

### Error 2: `register` en un componente controlado
**Mal:** `<TextField select {...register('tipo')}>` (el select no se actualiza).
**Bien:** envolver en `Controller`.

### Error 3: Montos como `number` en el schema
**Mal:** `monto: z.number()`.
**Bien:** `monto: z.string().refine(...)` + decimal.js para calcular.

### Error 4: `alert()`/`confirm()`/`console.log`
**Mal:** `if (confirm('¿seguro?'))`, `alert('error')`.
**Bien:** `useConfirm()`, `useSnackbar()`.

### Error 5: No deshabilitar durante el envío
Doble submit, doble creación. Usá `disabled={saving}`.

### Error 6: Mensajes de error en inglés o genéricos
**Mal:** `'Invalid'`, `'Error'`. **Bien:** "El monto debe ser mayor a 0".

### Error 7: No invalidar el caché tras mutar
La lista no refleja el alta. `queryClient.invalidateQueries({ queryKey: ...all() })`.

## Checklist antes de cerrar

- [ ] `useForm` + `zodResolver` + `mode: 'onBlur'` + `defaultValues` tipados.
- [ ] Schema zod en `schemas/<dominio>.schemas.ts` con `z.infer` exportado.
- [ ] `register` para texto/número; `Controller` para select/checkbox/custom.
- [ ] `error`/`helperText` por campo; error de servidor en Alert/snackbar.
- [ ] `disabled={saving}` en inputs y botón; texto "Guardando…".
- [ ] Mutación invalida el caché + navega + `snackbar.success`.
- [ ] Montos como string + decimal.js (no float).
- [ ] Sin `alert`/`confirm`/`console.log`.
- [ ] `npx tsc -b`, `npm run lint`, `npm test -- --run` verdes.

## Referencias

- `pages/Finanzas/Monedas/MonedaFormPage.tsx`, `schemas/*.schemas.ts`,
  `hooks/useDocumentoVentaBase.ts`, `contexts/FeedbackContext.tsx` +
  `feedbackTypes.ts`, `utils/fuzzyDuplicate.ts`.
- Skills: `omni-frontend-page`, `omni-frontend-data`, `omni-money-ui`,
  `omni-design-system`, `omni-pr-discipline`.

## Changelog

### v1.0 — 2026-06-03
- Versión inicial (alineada a FE-CRIT-1 y la rama frontend-forms-reskin).

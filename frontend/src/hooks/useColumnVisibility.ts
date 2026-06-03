import { useCallback, useState } from 'react';

export interface ColumnDef<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  /** Columna fija: no puede ocultarse. */
  always?: boolean;
  /** Visible por defecto (si no es `always`). */
  defaultVisible?: boolean;
  render: (row: T, index: number) => React.ReactNode;
}

type Visibility = Record<string, boolean>;

function buildDefaults<T>(columns: ColumnDef<T>[]): Visibility {
  const o: Visibility = {};
  for (const c of columns) o[c.key] = !!(c.always || c.defaultVisible);
  return o;
}

function load<T>(storageKey: string, columns: ColumnDef<T>[]): Visibility {
  const defaults = buildDefaults(columns);
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return defaults;
    const saved = JSON.parse(raw) as Visibility;
    // Mezcla: respeta lo guardado pero fuerza las columnas fijas y descarta claves obsoletas.
    const merged: Visibility = {};
    for (const c of columns) {
      merged[c.key] = c.always ? true : saved[c.key] ?? defaults[c.key];
    }
    return merged;
  } catch {
    return defaults;
  }
}

/**
 * Visibilidad de columnas configurable (estilo Odoo) con persistencia en
 * localStorage por `storageKey`. Las columnas `always` quedan siempre visibles.
 */
export function useColumnVisibility<T>(storageKey: string, columns: ColumnDef<T>[]) {
  const [visible, setVisible] = useState<Visibility>(() => load(storageKey, columns));

  const persist = useCallback(
    (next: Visibility) => {
      setVisible(next);
      try {
        localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        /* almacenamiento no disponible — se mantiene en memoria */
      }
    },
    [storageKey],
  );

  const toggle = useCallback(
    (key: string) => {
      const col = columns.find((c) => c.key === key);
      if (!col || col.always) return;
      persist({ ...visible, [key]: !visible[key] });
    },
    [columns, visible, persist],
  );

  const isVisible = useCallback((key: string) => !!visible[key], [visible]);

  return { visible, isVisible, toggle };
}

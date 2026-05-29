import type { CuotaPreview } from '../types/cxc';

export interface CuotasParams {
  fechaInicio: string;         // ISO date string
  plazoTotalDias: number;
  periodicidad: 'unico' | 'semanal' | 'quincenal' | 'mensual';
  montoTotal: number;
  montoCuota?: number;
  porcentajeAbono?: number;
}

function proximaFecha(base: Date, periodicidad: string, n: number): Date {
  const d = new Date(base);
  if (periodicidad === 'semanal') {
    d.setDate(d.getDate() + 7 * n);
  } else if (periodicidad === 'quincenal') {
    d.setDate(d.getDate() + 15 * n);
  } else if (periodicidad === 'mensual') {
    d.setMonth(d.getMonth() + n);
  }
  return d;
}

export function calcularCuotasPreview(params: CuotasParams): CuotaPreview[] {
  const { fechaInicio, plazoTotalDias, periodicidad, montoTotal, montoCuota, porcentajeAbono } = params;
  const base = new Date(fechaInicio);

  if (periodicidad === 'unico') {
    return [{
      numero: 1,
      fecha_vencimiento: fechaInicio,
      monto: Math.round(montoTotal * 100) / 100,
    }];
  }

  const diasPorCuota = periodicidad === 'semanal' ? 7 : periodicidad === 'quincenal' ? 15 : 30;
  const numCuotas = Math.max(1, Math.floor(plazoTotalDias / diasPorCuota));

  let montoUnit: number;
  if (montoCuota) {
    montoUnit = Math.round(montoCuota * 100) / 100;
  } else if (porcentajeAbono) {
    montoUnit = Math.round((montoTotal * porcentajeAbono / 100) * 100) / 100;
  } else {
    montoUnit = Math.round((montoTotal / numCuotas) * 100) / 100;
  }

  const cuotas: CuotaPreview[] = [];
  let acumulado = 0;

  for (let i = 1; i <= numCuotas; i++) {
    const fecha = proximaFecha(base, periodicidad, i - 1);
    const monto = i === numCuotas
      ? Math.round((montoTotal - acumulado) * 100) / 100
      : montoUnit;

    if (monto <= 0) continue;

    cuotas.push({
      numero: i,
      fecha_vencimiento: fecha.toISOString().split('T')[0],
      monto,
    });
    acumulado += monto;
  }

  return cuotas;
}

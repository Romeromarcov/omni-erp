import Decimal from 'decimal.js';
import { D, type DecimalInput } from '../lib/decimal';
import type { CuotaPreview } from '../types/cxc';

export interface CuotasParams {
  fechaInicio: string;         // ISO date string
  plazoTotalDias: number;
  periodicidad: 'unico' | 'semanal' | 'quincenal' | 'mensual';
  montoTotal: DecimalInput;
  montoCuota?: DecimalInput;
  porcentajeAbono?: DecimalInput;
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
  const totalDec = D(montoTotal);

  if (periodicidad === 'unico') {
    return [{
      numero: 1,
      fecha_vencimiento: fechaInicio,
      monto: totalDec.toDecimalPlaces(2).toFixed(2),
    }];
  }

  const diasPorCuota = periodicidad === 'semanal' ? 7 : periodicidad === 'quincenal' ? 15 : 30;
  const numCuotas = Math.max(1, Math.floor(plazoTotalDias / diasPorCuota));

  let montoUnit: Decimal;
  if (montoCuota !== undefined && montoCuota !== null && montoCuota !== '' && D(montoCuota).gt(0)) {
    montoUnit = D(montoCuota).toDecimalPlaces(2);
  } else if (porcentajeAbono !== undefined && porcentajeAbono !== null && porcentajeAbono !== '' && D(porcentajeAbono).gt(0)) {
    montoUnit = totalDec.times(D(porcentajeAbono)).dividedBy(100).toDecimalPlaces(2);
  } else {
    montoUnit = totalDec.dividedBy(numCuotas).toDecimalPlaces(2);
  }

  const cuotas: CuotaPreview[] = [];
  let acumulado = new Decimal(0);

  for (let i = 1; i <= numCuotas; i++) {
    const fecha = proximaFecha(base, periodicidad, i - 1);
    const monto = i === numCuotas
      ? totalDec.minus(acumulado).toDecimalPlaces(2)
      : montoUnit;

    if (monto.lte(0)) continue;

    cuotas.push({
      numero: i,
      fecha_vencimiento: fecha.toISOString().split('T')[0],
      monto: monto.toFixed(2),
    });
    acumulado = acumulado.plus(monto);
  }

  return cuotas;
}

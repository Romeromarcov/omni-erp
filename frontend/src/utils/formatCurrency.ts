export function formatCurrency(value: number | string, currency: string = 'USD') {
  const num = typeof value === 'string' ? parseFloat(value) : value;
  return num.toLocaleString('en-US', { style: 'currency', currency });
}

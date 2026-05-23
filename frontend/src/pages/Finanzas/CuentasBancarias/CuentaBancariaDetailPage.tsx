import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import PageLayout from '../../../components/PageLayout';
import { getCuentaBancariaDetail, updateCuentaBancaria } from '../../../services/cuentaBancariaService';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { toList } from '../../../utils/api';
import { Button, TextField } from '@mui/material';

interface CuentaBancaria {
  nombre_banco: string;
  tipo_cuenta: string;
  numero_cuenta: string;
  id_moneda: string;
  activo: boolean;
  metodos_pago: string[];
}
type MetodoPagoEmpresaActiva = {
  id: string;
  metodo_pago: string; // UUID
  nombre?: string;
  metodo_pago_nombre?: string;
  nombre_metodo?: string;
};

const CuentaBancariaDetailPage: React.FC = () => {
  const { id_cuenta } = useParams<{ id_cuenta: string }>();
  const navigate = useNavigate();
  const empresaId = localStorage.getItem('id_empresa') || '';
  const [form, setForm] = useState<CuentaBancaria>({
    nombre_banco: '',
    tipo_cuenta: '',
    numero_cuenta: '',
    id_moneda: '',
    activo: true,
    metodos_pago: [],
  });
  const [error, setError] = useState('');

  const { data: cuentaData, isLoading } = useQuery<CuentaBancaria>({
    queryKey: [`/finanzas/cuentas-bancarias/${id_cuenta}/`],
    queryFn: () => getCuentaBancariaDetail(id_cuenta!) as Promise<CuentaBancaria>,
    enabled: !!id_cuenta,
  });

  useEffect(() => {
    if (cuentaData) {
      setForm({
        nombre_banco: cuentaData?.nombre_banco || '',
        tipo_cuenta: cuentaData?.tipo_cuenta || '',
        numero_cuenta: cuentaData?.numero_cuenta || '',
        id_moneda: cuentaData?.id_moneda || '',
        activo: cuentaData?.activo !== undefined ? cuentaData.activo : true,
        metodos_pago: Array.isArray(cuentaData?.metodos_pago) ? cuentaData.metodos_pago : [],
      });
    }
  }, [cuentaData]);

  const { data: monedas = [] } = useQuery<Moneda[], Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/'],
    queryFn: () => fetchMonedas(),
  });

  const { data: metodosPago = [] } = useQuery<unknown, Error, MetodoPagoEmpresaActiva[]>({
    queryKey: [`/finanzas/metodos-pago-empresa-activos/${empresaId}/`],
    queryFn: () => fetchMetodosPagoEmpresaActivos(empresaId),
    select: toList,
    enabled: !!empresaId,
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      const id_empresa = localStorage.getItem('id_empresa') || '';
      return updateCuentaBancaria(id_cuenta!, { ...form, metodos_pago: form.metodos_pago, id_empresa });
    },
    onSuccess: () => navigate(-1),
    onError: () => setError('Error al actualizar la cuenta bancaria'),
  });

  const loading = isLoading || updateMutation.isPending;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const { name, value, type } = target;
    if (target instanceof HTMLSelectElement && target.multiple) {
      const selected: string[] = Array.from(target.selectedOptions).map(opt => opt.value);
      setForm(f => ({ ...f, [name]: selected }));
    } else {
      setForm(f => ({
        ...f,
        [name]: type === 'checkbox' ? (target as HTMLInputElement).checked : value
      }));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_cuenta) return;
    setError('');
    updateMutation.mutate();
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Detalle de Cuenta Bancaria</h2>
      <form onSubmit={handleSubmit} style={{ maxWidth: 400 }}>
        <TextField fullWidth label="Banco" name="nombre_banco" value={form.nombre_banco} onChange={handleChange as React.ChangeEventHandler<HTMLInputElement>} required />
        <label>Tipo de Cuenta</label>
        <select name="tipo_cuenta" value={form.tipo_cuenta} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione un tipo</option>
          <option value="AHORRO">Ahorro</option>
          <option value="CORRIENTE">Corriente</option>
          <option value="CREDITO">Crédito</option>
        </select>
        <TextField fullWidth label="Número de Cuenta" name="numero_cuenta" value={form.numero_cuenta} onChange={handleChange as React.ChangeEventHandler<HTMLInputElement>} required />
        <label>Moneda</label>
        <select name="id_moneda" value={form.id_moneda} onChange={handleChange} required style={{ width: '100%', marginBottom: 16, padding: 8 }}>
          <option value="">Seleccione una moneda</option>
          {monedas.map(m => <option key={m.id_moneda} value={m.id_moneda}>{m.nombre}</option>)}
        </select>
        <label>Métodos de Pago</label>
        <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>
          Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varios métodos.
        </div>
        <select
          name="metodos_pago"
          multiple
          value={form.metodos_pago}
          onChange={handleChange}
          required={metodosPago.length > 0}
          style={{ width: '100%', marginBottom: 16, padding: 8, minHeight: 60 }}
        >
          {metodosPago.map(mp => (
            <option key={mp.metodo_pago} value={mp.metodo_pago}>
              {mp.nombre || mp.nombre_metodo || mp.metodo_pago_nombre || mp.metodo_pago}
            </option>
          ))}
        </select>
        <label>
          <input type="checkbox" name="activo" checked={form.activo} onChange={handleChange} /> Activa
        </label>
        {error && <div style={{ color: 'red', marginTop: 8 }}>{error}</div>}
        <div style={{ marginTop: 16 }}>
          <Button type="submit" disabled={loading}>{loading ? 'Guardando...' : 'Guardar Cambios'}</Button>
          <Button type="button" onClick={() => navigate(-1)} style={{ marginLeft: 8 }}>Cancelar</Button>
        </div>
      </form>
    </PageLayout>
  );
};

export default CuentaBancariaDetailPage;

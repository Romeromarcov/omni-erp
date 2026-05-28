import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../contexts/AuthContext';
import PageLayout from '../../components/PageLayout';
import {
  configuracionFiscalService,
  tasaIVAService,
  type ConfiguracionFiscalEmpresa,
  type TasaIVAEmpresa,
} from '../../services/fiscalService';

interface FiscalForm {
  contribuyente_iva: boolean;
  aplica_igtf: boolean;
  tasa_igtf: string;
}

const TIPOS_IVA = ['GENERAL', 'REDUCIDO', 'EXENTO', 'ADICIONAL'] as const;

const ConfiguracionFiscalPage: React.FC = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const empresaId = user?.empresas?.[0]?.id_empresa ?? '';

  const [form, setForm] = useState<FiscalForm>({
    contribuyente_iva: true,
    aplica_igtf: true,
    tasa_igtf: '0.03',
  });
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // ── Load existing config ──────────────────────────────────────────────────

  const { data: config, isLoading } = useQuery<ConfiguracionFiscalEmpresa | null>({
    queryKey: ['configuracion-fiscal', empresaId],
    queryFn: () => configuracionFiscalService.getByEmpresa(empresaId),
    enabled: !!empresaId,
  });

  const { data: tasas = [] } = useQuery<TasaIVAEmpresa[]>({
    queryKey: ['tasas-iva', empresaId],
    queryFn: () => tasaIVAService.getByEmpresa(empresaId),
    enabled: !!empresaId,
  });

  useEffect(() => {
    if (config) {
      setForm({
        contribuyente_iva: config.contribuyente_iva,
        aplica_igtf: config.aplica_igtf,
        tasa_igtf: config.tasa_igtf,
      });
    }
  }, [config]);

  // ── Mutations ─────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!empresaId) throw new Error('No hay empresa activa.');
      const payload = {
        ...form,
        tasa_igtf: parseFloat(form.tasa_igtf).toFixed(4),
        id_empresa: empresaId,
      };
      if (config) {
        return configuracionFiscalService.update(config.id, payload);
      }
      return configuracionFiscalService.create(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['configuracion-fiscal', empresaId] });
      setSuccessMsg('Configuración fiscal guardada correctamente.');
      setErrorMsg('');
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
      setSuccessMsg('');
    },
  });

  // ── Render ────────────────────────────────────────────────────────────────

  const labelStyle: React.CSSProperties = { fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 };
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '9px 12px',
    border: '1px solid #dee2e6',
    borderRadius: 8,
    fontSize: 14,
    boxSizing: 'border-box',
  };

  return (
    <PageLayout maxWidth={700}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 700 }}>Configuración Fiscal</h2>
        <p style={{ color: '#6c757d', fontSize: 14, margin: 0 }}>
          Parámetros de IVA e IGTF para la empresa.
        </p>
      </div>

      {successMsg && (
        <div style={{ background: '#e8f5e9', border: '1px solid #4caf50', borderRadius: 8, padding: '12px 16px', marginBottom: 20, color: '#2e7d32', fontWeight: 600 }}>
          ✅ {successMsg}
        </div>
      )}
      {errorMsg && (
        <div style={{ background: '#ffebee', border: '1px solid #f44336', borderRadius: 8, padding: '12px 16px', marginBottom: 20, color: '#c62828' }}>
          ⚠️ {errorMsg}
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#6c757d' }}>Cargando configuración…</div>
      ) : (
        <form
          onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }}
          style={{ display: 'flex', flexDirection: 'column', gap: 20 }}
        >
          {/* Section: IVA */}
          <div style={{ border: '1px solid #dee2e6', borderRadius: 10, padding: 20 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#1976d2' }}>
              📋 Impuesto al Valor Agregado (IVA)
            </h3>

            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14, cursor: 'pointer', marginBottom: 0 }}>
              <input
                type="checkbox"
                checked={form.contribuyente_iva}
                onChange={(e) => setForm((f) => ({ ...f, contribuyente_iva: e.target.checked }))}
                style={{ width: 16, height: 16 }}
              />
              <span>
                <strong>Contribuyente ordinario de IVA</strong>
                <span style={{ color: '#6c757d', fontSize: 13, display: 'block' }}>
                  La empresa está inscrita como contribuyente del IVA ante el SENIAT.
                </span>
              </span>
            </label>
          </div>

          {/* Section: IGTF */}
          <div style={{ border: '1px solid #dee2e6', borderRadius: 10, padding: 20 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: '#e65100' }}>
              💱 Impuesto a las Grandes Transacciones Financieras (IGTF)
            </h3>

            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14, cursor: 'pointer', marginBottom: 16 }}>
              <input
                type="checkbox"
                checked={form.aplica_igtf}
                onChange={(e) => setForm((f) => ({ ...f, aplica_igtf: e.target.checked }))}
                style={{ width: 16, height: 16 }}
              />
              <span>
                <strong>Aplicar IGTF en pagos en divisas/crypto</strong>
                <span style={{ color: '#6c757d', fontSize: 13, display: 'block' }}>
                  Se aplica IGTF cuando el cliente paga en moneda extranjera o criptomoneda.
                </span>
              </span>
            </label>

            {form.aplica_igtf && (
              <div>
                <label style={labelStyle}>
                  Alícuota IGTF (decimal, ej: 0.03 = 3%)
                </label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.001"
                  value={form.tasa_igtf}
                  onChange={(e) => setForm((f) => ({ ...f, tasa_igtf: e.target.value }))}
                  style={{ ...inputStyle, maxWidth: 200 }}
                />
                <span style={{ fontSize: 13, color: '#6c757d', marginLeft: 8 }}>
                  = {(parseFloat(form.tasa_igtf || '0') * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>

          {/* Section: Tasas IVA */}
          {tasas.length > 0 && (
            <div style={{ border: '1px solid #dee2e6', borderRadius: 10, padding: 20 }}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700, color: '#2e7d32' }}>
                📊 Tasas de IVA configuradas
              </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: '#f8f9fa' }}>
                      {['Tipo', 'Nombre', 'Tasa', 'Estado'].map((h) => (
                        <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tasas.map((t) => (
                      <tr key={t.id} style={{ borderBottom: '1px solid #dee2e6' }}>
                        <td style={{ padding: '8px 12px' }}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 600,
                            background: TIPOS_IVA.indexOf(t.tipo) === 0 ? '#1976d2' : '#6c757d',
                            color: '#fff',
                          }}>
                            {t.tipo}
                          </span>
                        </td>
                        <td style={{ padding: '8px 12px' }}>{t.nombre}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 700 }}>
                          {(parseFloat(t.tasa) * 100).toFixed(0)}%
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <span style={{ color: t.activo ? '#4caf50' : '#f44336', fontSize: 12, fontWeight: 600 }}>
                            {t.activo ? 'Activo' : 'Inactivo'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Submit */}
          <div style={{ paddingTop: 4 }}>
            <button
              type="submit"
              disabled={saveMutation.isPending || !empresaId}
              style={{
                padding: '12px 32px',
                background: saveMutation.isPending ? '#bdbdbd' : '#1976d2',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                cursor: saveMutation.isPending ? 'not-allowed' : 'pointer',
                fontWeight: 700,
                fontSize: 15,
              }}
            >
              {saveMutation.isPending ? 'Guardando…' : 'Guardar configuración'}
            </button>
          </div>
        </form>
      )}
    </PageLayout>
  );
};

export default ConfiguracionFiscalPage;

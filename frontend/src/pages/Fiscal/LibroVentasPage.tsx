import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../contexts/AuthContext';
import PageLayout from '../../components/PageLayout';
import { libroService, type LibroEntry } from '../../services/fiscalService';

function currentPeriodo(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const LibroVentasPage: React.FC = () => {
  const { user } = useAuth();
  const empresaId = user?.empresas?.[0]?.id_empresa ?? '';

  const [periodo, setPeriodo] = useState(currentPeriodo());
  const [queryPeriodo, setQueryPeriodo] = useState('');
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState(false);

  const { data: entries = [], isLoading, isError, error } = useQuery<LibroEntry[]>({
    queryKey: ['libro-ventas', empresaId, queryPeriodo],
    queryFn: () => libroService.fetchLibroVentasTxt(empresaId, queryPeriodo),
    enabled: !!empresaId && !!queryPeriodo,
  });

  function handleConsultar() {
    if (periodo) setQueryPeriodo(periodo);
  }

  async function handleDownload() {
    setDownloadError('');
    setDownloading(true);
    try {
      await libroService.downloadLibroVentasTxt(empresaId, queryPeriodo);
    } catch (e) {
      setDownloadError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }

  const totalBase = entries.reduce((s, e) => s + parseFloat(e.base_imponible || '0'), 0);
  const totalIva = entries.reduce((s, e) => s + parseFloat(e.iva || '0'), 0);
  const totalTotal = entries.reduce((s, e) => s + parseFloat(e.total || '0'), 0);

  return (
    <PageLayout maxWidth={1100}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 700 }}>Libro de Ventas — SENIAT</h2>
        <p style={{ color: '#6c757d', fontSize: 14, margin: 0 }}>
          Consulta y exporta el libro de ventas en formato TXT SENIAT.
        </p>
      </div>

      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Período (AAAA-MM)
          </label>
          <input
            type="month"
            value={periodo}
            onChange={(e) => setPeriodo(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #dee2e6', borderRadius: 8, fontSize: 14 }}
          />
        </div>
        <button
          onClick={handleConsultar}
          disabled={!periodo || !empresaId}
          style={{
            padding: '9px 20px',
            background: '#1976d2',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          Consultar
        </button>
        {queryPeriodo && entries.length > 0 && (
          <button
            onClick={handleDownload}
            disabled={downloading}
            style={{
              padding: '9px 20px',
              background: '#2e7d32',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: downloading ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            {downloading ? 'Descargando…' : '⬇ Exportar TXT'}
          </button>
        )}
      </div>

      {downloadError && (
        <div style={{ background: '#ffebee', border: '1px solid #f44336', borderRadius: 8, padding: '10px 14px', marginBottom: 16, color: '#c62828', fontSize: 14 }}>
          ⚠️ {downloadError}
        </div>
      )}

      {/* Results */}
      {isLoading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#6c757d' }}>Cargando libro…</div>
      )}

      {isError && (
        <div style={{ background: '#ffebee', border: '1px solid #f44336', borderRadius: 8, padding: '12px 16px', color: '#c62828' }}>
          ⚠️ {(error as Error)?.message ?? 'Error al cargar el libro de ventas.'}
        </div>
      )}

      {!isLoading && !isError && queryPeriodo && entries.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: '#6c757d' }}>
          No hay facturas en el período {queryPeriodo}.
        </div>
      )}

      {entries.length > 0 && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            {[
              { label: 'Facturas', value: String(entries.length), color: '#1976d2' },
              { label: 'Base imponible', value: totalBase.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }), color: '#2e7d32' },
              { label: 'IVA', value: totalIva.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }), color: '#e65100' },
              { label: 'Total', value: totalTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }), color: '#6a1b9a' },
            ].map((c) => (
              <div key={c.label} style={{ flex: 1, minWidth: 140, padding: '12px 16px', border: `2px solid ${c.color}`, borderRadius: 10, background: '#fff' }}>
                <div style={{ fontSize: 12, color: '#6c757d', marginBottom: 2 }}>{c.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: c.color }}>{c.value}</div>
              </div>
            ))}
          </div>

          {/* Table */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f8f9fa' }}>
                  {['RIF Emisor', 'RIF Receptor', 'Fecha', 'Nro. Control', 'Nro. Factura', 'Base Imponible', 'IVA', 'Total'].map((h) => (
                    <th key={h} style={{ padding: '8px 10px', textAlign: h === 'RIF Emisor' || h === 'RIF Receptor' ? 'left' : 'right', borderBottom: '2px solid #dee2e6', whiteSpace: 'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entries.map((e, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #dee2e6' }}>
                    <td style={{ padding: '7px 10px' }}>{e.rif_emisor}</td>
                    <td style={{ padding: '7px 10px' }}>{e.rif_receptor}</td>
                    <td style={{ padding: '7px 10px', whiteSpace: 'nowrap' }}>{e.fecha}</td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>{e.nro_ctrl}</td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>{e.nro_fac}</td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                      {parseFloat(e.base_imponible || '0').toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                      {parseFloat(e.iva || '0').toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 600 }}>
                      {parseFloat(e.total || '0').toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
                {/* Totals row */}
                <tr style={{ background: '#f8f9fa', fontWeight: 700 }}>
                  <td colSpan={5} style={{ padding: '8px 10px', borderTop: '2px solid #dee2e6' }}>TOTALES</td>
                  <td style={{ padding: '8px 10px', textAlign: 'right', borderTop: '2px solid #dee2e6' }}>
                    {totalBase.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'right', borderTop: '2px solid #dee2e6' }}>
                    {totalIva.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'right', borderTop: '2px solid #dee2e6' }}>
                    {totalTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </PageLayout>
  );
};

export default LibroVentasPage;

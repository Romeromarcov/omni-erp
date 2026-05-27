import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getConector,
  testConector,
  triggerSync,
  getJobsDeConector,
  type JobSincronizacion,
} from '../../services/integrationHubService';

const ESTADO_JOB_COLORS: Record<string, { bg: string; text: string }> = {
  completado:             { bg: '#e6f4ea', text: '#1e7e34' },
  completado_con_errores: { bg: '#fff3cd', text: '#856404' },
  fallido:                { bg: '#fde8e8', text: '#b91c1c' },
  en_progreso:            { bg: '#eff6ff', text: '#1d4ed8' },
  pendiente:              { bg: '#f3f4f6', text: '#6b7280' },
};

const ESTADO_CONECTOR_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  activo:       { bg: '#e6f4ea', text: '#1e7e34', label: 'Activo' },
  configurando: { bg: '#fff3cd', text: '#856404', label: 'Configurando' },
  error:        { bg: '#fde8e8', text: '#b91c1c', label: 'Error' },
  inactivo:     { bg: '#f3f4f6', text: '#6b7280', label: 'Inactivo' },
};

const JobRow: React.FC<{ job: JobSincronizacion }> = ({ job }) => {
  const col = ESTADO_JOB_COLORS[job.estado] ?? ESTADO_JOB_COLORS.pendiente;
  const inicio = job.iniciado_en
    ? new Date(job.iniciado_en).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })
    : '—';
  const duracion = job.duracion_segundos != null
    ? `${job.duracion_segundos}s`
    : '—';

  return (
    <tr style={{ borderBottom: '1px solid #f3f4f6' }}>
      <td style={{ padding: '10px 12px', fontSize: 13 }}>{job.tipo_entidad}</td>
      <td style={{ padding: '10px 12px' }}>
        <span style={{ ...col, padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
          {job.estado.replace(/_/g, ' ')}
        </span>
      </td>
      <td style={{ padding: '10px 12px', fontSize: 13, color: '#6b7280' }}>{inicio}</td>
      <td style={{ padding: '10px 12px', fontSize: 13, textAlign: 'right' }}>
        {job.creados > 0 && <span style={{ color: '#16a34a', marginRight: 6 }}>+{job.creados}</span>}
        {job.actualizados > 0 && <span style={{ color: '#2563eb', marginRight: 6 }}>↺{job.actualizados}</span>}
        {job.omitidos > 0 && <span style={{ color: '#9ca3af', marginRight: 6 }}>={job.omitidos}</span>}
        {job.fallidos > 0 && <span style={{ color: '#dc2626' }}>✕{job.fallidos}</span>}
      </td>
      <td style={{ padding: '10px 12px', fontSize: 12, color: '#9ca3af', textAlign: 'right' }}>{duracion}</td>
    </tr>
  );
};

const ConectorDetallePage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [syncEntidad, setSyncEntidad] = useState('');
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; version?: string } | null>(null);

  const { data: conector, isLoading } = useQuery({
    queryKey: [`/integration-hub/instancias/${id}/`],
    queryFn: () => getConector(id!),
    enabled: !!id,
  });

  const { data: jobsData } = useQuery({
    queryKey: [`/integration-hub/instancias/${id}/jobs/`],
    queryFn: () => getJobsDeConector(id!),
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const testMutation = useMutation({
    mutationFn: () => testConector(id!),
    onSuccess: res => setTestResult(res),
    onError: (e: Error) => setTestResult({ success: false, message: e.message }),
  });

  const syncMutation = useMutation({
    mutationFn: () => triggerSync(id!, syncEntidad),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [`/integration-hub/instancias/${id}/jobs/`] });
      qc.invalidateQueries({ queryKey: ['/integration-hub/status/'] });
    },
  });

  if (isLoading) return <div style={{ padding: 40, color: '#9ca3af' }}>Cargando…</div>;
  if (!conector) return <div style={{ padding: 40, color: '#dc2626' }}>Conector no encontrado.</div>;

  const estadoConector = ESTADO_CONECTOR_COLORS[conector.estado] ?? ESTADO_CONECTOR_COLORS.inactivo;
  const jobs = jobsData?.results ?? [];

  const btn = (primary?: boolean, danger?: boolean): React.CSSProperties => ({
    padding: '8px 16px',
    borderRadius: 6,
    border: 'none',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 13,
    background: primary ? '#2563eb' : danger ? '#dc2626' : '#f3f4f6',
    color: primary || danger ? '#fff' : '#374151',
  });

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1000 }}>
      {/* Back */}
      <button
        onClick={() => navigate('/integraciones')}
        style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 13, marginBottom: 16, padding: 0 }}
      >
        ← Volver al Integration Hub
      </button>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#111827' }}>{conector.nombre}</h1>
            <span style={{
              padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
              background: estadoConector.bg, color: estadoConector.text,
            }}>
              {estadoConector.label}
            </span>
          </div>
          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
            {conector.proveedor_nombre}
            {conector.version_detectada && ` · v${conector.version_detectada}`}
          </div>
        </div>
        <button
          style={btn(false, false)}
          onClick={() => { testMutation.reset(); setTestResult(null); testMutation.mutate(); }}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? 'Probando…' : '🔌 Probar conexión'}
        </button>
      </div>

      {/* Test result */}
      {testResult && (
        <div style={{
          background: testResult.success ? '#e6f4ea' : '#fde8e8',
          border: `1px solid ${testResult.success ? '#86efac' : '#fca5a5'}`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 20,
          fontSize: 13, color: testResult.success ? '#166534' : '#b91c1c',
        }}>
          {testResult.success ? '✓' : '✕'} {testResult.message}
          {testResult.version && <span style={{ marginLeft: 8, opacity: 0.7 }}>({testResult.version})</span>}
        </div>
      )}

      {/* Config info */}
      <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 20px', marginBottom: 24 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10, color: '#374151' }}>Configuración</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 24px', fontSize: 13 }}>
          {conector.configuracion_publica?.host && (
            <>
              <span style={{ color: '#9ca3af' }}>Host</span>
              <span style={{ fontFamily: 'monospace' }}>{conector.configuracion_publica.host}</span>
            </>
          )}
          {conector.configuracion_publica?.user && (
            <>
              <span style={{ color: '#9ca3af' }}>Usuario</span>
              <span>{conector.configuracion_publica.user}</span>
            </>
          )}
          <span style={{ color: '#9ca3af' }}>Intervalo sync</span>
          <span>Cada {conector.intervalo_sync_minutos} min</span>
          <span style={{ color: '#9ca3af' }}>Último sync</span>
          <span>{conector.ultimo_sync ? new Date(conector.ultimo_sync).toLocaleString('es-VE') : 'Nunca'}</span>
        </div>

        {conector.entidades_activas.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <span style={{ color: '#9ca3af', fontSize: 13 }}>Entidades: </span>
            {conector.entidades_activas.map(e => (
              <span key={e} style={{ background: '#eff6ff', color: '#1d4ed8', borderRadius: 4, padding: '2px 6px', fontSize: 11, fontWeight: 500, marginRight: 4 }}>
                {e}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Disparar sync */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 20px', marginBottom: 24 }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10, color: '#374151' }}>Sincronización manual</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <select
            value={syncEntidad}
            onChange={e => setSyncEntidad(e.target.value)}
            style={{ flex: 1, padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', fontSize: 13 }}
          >
            <option value="">Seleccionar entidad…</option>
            {conector.entidades_activas.map(e => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
          <button
            style={btn(true)}
            disabled={!syncEntidad || syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            {syncMutation.isPending ? 'Iniciando…' : '▶ Sincronizar'}
          </button>
        </div>
        {syncMutation.isSuccess && syncMutation.data?.job_id && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#16a34a' }}>
            ✓ Job iniciado — {syncMutation.data.mensaje}
          </div>
        )}
        {syncMutation.isError && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#dc2626' }}>
            Error: {(syncMutation.error as Error).message}
          </div>
        )}
      </div>

      {/* Jobs recientes */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid #f3f4f6', fontWeight: 600, fontSize: 14, color: '#111827' }}>
          Jobs recientes
        </div>
        {jobs.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
            Sin jobs registrados aún.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f9fafb' }}>
                  {['Entidad', 'Estado', 'Inicio', 'Registros', 'Duración'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: h === 'Registros' || h === 'Duración' ? 'right' : 'left', fontSize: 11, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map(j => <JobRow key={j.id_job} job={j} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConectorDetallePage;

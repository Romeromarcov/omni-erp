import React, { useEffect, useState, useMemo } from 'react';
import { fetchAuditLogs } from '../../../services/auditoria';
import { fetchEmpresas } from '../../../services/empresas';
import { fetchUsuarios } from '../../../services/users';
import type { Usuario } from '../../../services/users';
import PageLayout from '../../../components/PageLayout';

// Types
export type AuditLog = {
  id: number;
  fecha_hora_accion: string;
  tipo_evento: string;
  modulo_afectado: string;
  nombre_modelo_afectado: string;
  id_registro_afectado: string;
  descripcion_accion: string;
  resultado_evento: string;
  id_usuario: number | { username: string };
  id_empresa: string | { nombre_legal: string };
};

export type Empresa = { id_empresa: string; nombre_legal?: string; };

const AuditLogListPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);

  // Filters
  const [filtroUsuario, setFiltroUsuario] = useState('');
  const [filtroTipoEvento, setFiltroTipoEvento] = useState('');
  const [filtroModulo, setFiltroModulo] = useState('');
  const [filtroModelo, setFiltroModelo] = useState('');
  const [filtroEmpresa, setFiltroEmpresa] = useState('');
  const [filtroResultado, setFiltroResultado] = useState('');
  const [filtroFechaInicio, setFiltroFechaInicio] = useState('');
  const [filtroFechaFin, setFiltroFechaFin] = useState('');

  const [selectedEmpresa, setSelectedEmpresa] = useState<string>('');

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchEmpresas()
      .then(async (empresasData: unknown) => {
        let empresasArr: Empresa[] = [];
        if (Array.isArray(empresasData)) {
          empresasArr = empresasData as Empresa[];
        } else if (empresasData && Array.isArray((empresasData as { results?: unknown[] }).results)) {
          empresasArr = (empresasData as { results: Empresa[] }).results;
        }
        setEmpresas(empresasArr);
        let empresaId = selectedEmpresa || (empresasArr.length > 0 ? empresasArr[0].id_empresa : '');
        // Elimina cualquier sufijo tipo ':1' que pueda venir del value del select
        if (empresaId.includes(':')) empresaId = empresaId.split(':')[0];
        setSelectedEmpresa(empresaId);
        const [logsData, usuariosData] = await Promise.all([
          fetchAuditLogs(),
          fetchUsuarios(empresaId)
        ]);
        // Type guard for paginated response
        const isPaginated = (data: unknown): data is { results: AuditLog[] } => {
          return !!data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results);
        };
        if (Array.isArray(logsData)) {
          setLogs(logsData as AuditLog[]);
        } else if (isPaginated(logsData)) {
          setLogs((logsData as { results: AuditLog[] }).results);
        } else {
          setLogs([]);
          setError('La respuesta del servidor no es una lista de registros.');
        }
        setUsuarios((usuariosData || []) as Usuario[]);
      })
      .catch(err => {
        setLogs([]);
        setEmpresas([]);
        setUsuarios([]);
        try {
          const msg = JSON.parse(err.message)?.detail || err.message;
          setError(msg);
        } catch {
          setError(err.message);
        }
      })
      .finally(() => setLoading(false));
  }, [selectedEmpresa]);

  // Filtering logic
  const filteredLogs = useMemo(() => logs.filter(l => {
    const usuario = typeof l.id_usuario === 'object' && l.id_usuario !== null ? l.id_usuario.username : usuarios.find(u => u.id === String(l.id_usuario))?.username || '';
    const empresa = typeof l.id_empresa === 'object' && l.id_empresa !== null ? l.id_empresa.nombre_legal : empresas.find(e => e.id_empresa === l.id_empresa)?.nombre_legal || '';
    const fecha = l.fecha_hora_accion.split('T')[0];
    return (
      (!filtroUsuario || usuario.toLowerCase().includes(filtroUsuario.toLowerCase())) &&
      (!filtroTipoEvento || l.tipo_evento.toLowerCase().includes(filtroTipoEvento.toLowerCase())) &&
      (!filtroModulo || l.modulo_afectado.toLowerCase().includes(filtroModulo.toLowerCase())) &&
      (!filtroModelo || l.nombre_modelo_afectado.toLowerCase().includes(filtroModelo.toLowerCase())) &&
      (!filtroEmpresa || empresa.toLowerCase().includes(filtroEmpresa.toLowerCase())) &&
      (!filtroResultado || l.resultado_evento.toLowerCase().includes(filtroResultado.toLowerCase())) &&
      (!filtroFechaInicio || fecha >= filtroFechaInicio) &&
      (!filtroFechaFin || fecha <= filtroFechaFin)
    );
  }), [logs, filtroUsuario, filtroTipoEvento, filtroModulo, filtroModelo, filtroEmpresa, filtroResultado, filtroFechaInicio, filtroFechaFin, empresas, usuarios]);

  // Export to CSV
  const exportCSV = () => {
    const header = ['Fecha/Hora', 'Tipo Evento', 'Módulo', 'Modelo', 'ID Registro', 'Descripción', 'Resultado', 'Usuario', 'Empresa'];
    const rows = filteredLogs.map(l => [
      l.fecha_hora_accion,
      l.tipo_evento,
      l.modulo_afectado,
      l.nombre_modelo_afectado,
      l.id_registro_afectado,
      l.descripcion_accion,
      l.resultado_evento,
      typeof l.id_usuario === 'object' && l.id_usuario !== null ? l.id_usuario.username : usuarios.find(u => u.id === String(l.id_usuario))?.username || '',
      typeof l.id_empresa === 'object' && l.id_empresa !== null ? l.id_empresa.nombre_legal : empresas.find(e => e.id_empresa === l.id_empresa)?.nombre_legal || ''
    ]);
    const csv = [header, ...rows].map(r => r.map(x => `"${(x ?? '').toString().replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'registro_auditoria.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Registro de Auditoría</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 18 }}>
        <select
          value={selectedEmpresa}
          onChange={e => setSelectedEmpresa(e.target.value)}
          style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 180 }}
        >
          {empresas.map(e => (
            <option key={e.id_empresa} value={e.id_empresa}>{e.nombre_legal || e.id_empresa}</option>
          ))}
        </select>
        <input placeholder="Usuario" value={filtroUsuario} onChange={e => setFiltroUsuario(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 120 }} />
        <input placeholder="Tipo evento" value={filtroTipoEvento} onChange={e => setFiltroTipoEvento(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 120 }} />
        <input placeholder="Módulo" value={filtroModulo} onChange={e => setFiltroModulo(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 120 }} />
        <input placeholder="Modelo" value={filtroModelo} onChange={e => setFiltroModelo(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 120 }} />
        <input placeholder="Empresa" value={filtroEmpresa} onChange={e => setFiltroEmpresa(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 120 }} />
        <input placeholder="Resultado" value={filtroResultado} onChange={e => setFiltroResultado(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc', minWidth: 120 }} />
        <input type="date" value={filtroFechaInicio} onChange={e => setFiltroFechaInicio(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc' }} />
        <input type="date" value={filtroFechaFin} onChange={e => setFiltroFechaFin(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #cfd8dc' }} />
        <button onClick={exportCSV} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', fontWeight: 600, fontSize: 15, cursor: 'pointer' }}>Exportar CSV</button>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : error ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32, fontWeight: 500 }}>{error}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Fecha/Hora</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Tipo Evento</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Módulo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Modelo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>ID Registro</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Descripción</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Resultado</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Usuario</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Empresa</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron registros.</td>
                </tr>
              ) : (
                filteredLogs.map(l => (
                  <tr key={l.id} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{l.fecha_hora_accion}</td>
                    <td style={{ padding: '10px 8px' }}>{l.tipo_evento}</td>
                    <td style={{ padding: '10px 8px' }}>{l.modulo_afectado}</td>
                    <td style={{ padding: '10px 8px' }}>{l.nombre_modelo_afectado}</td>
                    <td style={{ padding: '10px 8px' }}>{l.id_registro_afectado}</td>
                    <td style={{ padding: '10px 8px' }}>{l.descripcion_accion}</td>
                    <td style={{ padding: '10px 8px' }}>{l.resultado_evento}</td>
                    <td style={{ padding: '10px 8px' }}>{typeof l.id_usuario === 'object' && l.id_usuario !== null ? l.id_usuario.username : usuarios.find(u => u.id === String(l.id_usuario))?.username || '-'}</td>
                    <td style={{ padding: '10px 8px' }}>{typeof l.id_empresa === 'object' && l.id_empresa !== null ? l.id_empresa.nombre_legal : empresas.find(e => e.id_empresa === l.id_empresa)?.nombre_legal || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
};

export default AuditLogListPage;

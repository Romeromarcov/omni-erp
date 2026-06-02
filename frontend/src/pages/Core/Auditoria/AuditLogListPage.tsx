import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, MenuItem, Stack, TextField } from '@mui/material';
import { fetchAuditLogs } from '../../../services/auditoria';
import { fetchEmpresas } from '../../../services/empresas';
import { fetchUsuarios } from '../../../services/users';
import type { Usuario } from '../../../services/users';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';

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

  const { data: empresasRaw = [], isLoading: loadingEmpresas } = useQuery({
    queryKey: ['/core/empresas/'],
    queryFn: fetchEmpresas,
  });

  const empresas: Empresa[] = useMemo(
    () => (Array.isArray(empresasRaw) ? empresasRaw : []),
    [empresasRaw],
  );

  // Set selectedEmpresa to first empresa when loaded
  const efectiveEmpresa = selectedEmpresa || (empresas.length > 0 ? empresas[0].id_empresa : '');

  const { data: logsRaw, isLoading: loadingLogs, isError: errorLogs, error } = useQuery({
    queryKey: ['/auditoria/logs-auditoria/'],
    queryFn: fetchAuditLogs,
  });

  const { data: usuariosRaw = [] } = useQuery({
    queryKey: ['/core/usuarios/', efectiveEmpresa],
    queryFn: () => fetchUsuarios(efectiveEmpresa),
    enabled: !!efectiveEmpresa,
  });

  const logs: AuditLog[] = useMemo(() => {
    if (!logsRaw) return [];
    if (Array.isArray(logsRaw)) return logsRaw as AuditLog[];
    if (logsRaw && typeof logsRaw === 'object' && Array.isArray((logsRaw as { results?: unknown }).results)) {
      return (logsRaw as { results: AuditLog[] }).results;
    }
    return [];
  }, [logsRaw]);

  const usuarios: Usuario[] = useMemo(
    () => (Array.isArray(usuariosRaw) ? usuariosRaw : []),
    [usuariosRaw],
  );

  const loading = loadingEmpresas || loadingLogs;
  const errorMsg = errorLogs ? (error instanceof Error ? error.message : 'Error al cargar logs') : null;

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

  const columns: Column<AuditLog>[] = [
    { key: 'fecha', header: 'Fecha/Hora', render: (l) => l.fecha_hora_accion },
    { key: 'tipo', header: 'Tipo Evento', render: (l) => l.tipo_evento },
    { key: 'modulo', header: 'Módulo', render: (l) => l.modulo_afectado },
    { key: 'modelo', header: 'Modelo', render: (l) => l.nombre_modelo_afectado },
    { key: 'id_registro', header: 'ID Registro', render: (l) => l.id_registro_afectado },
    { key: 'descripcion', header: 'Descripción', render: (l) => l.descripcion_accion },
    { key: 'resultado', header: 'Resultado', render: (l) => l.resultado_evento },
    { key: 'usuario', header: 'Usuario', render: (l) => typeof l.id_usuario === 'object' && l.id_usuario !== null ? l.id_usuario.username : usuarios.find(u => u.id === String(l.id_usuario))?.username || '-' },
    { key: 'empresa', header: 'Empresa', render: (l) => typeof l.id_empresa === 'object' && l.id_empresa !== null ? l.id_empresa.nombre_legal : empresas.find(e => e.id_empresa === l.id_empresa)?.nombre_legal || '-' },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Registro de Auditoría"
        actions={<Button variant="contained" onClick={exportCSV}>Exportar CSV</Button>}
      />
      <Box sx={{ mb: 2 }}>
        <Stack direction="row" flexWrap="wrap" gap={1.5} useFlexGap>
          <TextField
            select
            size="small"
            label="Empresa"
            value={selectedEmpresa || efectiveEmpresa}
            onChange={e => setSelectedEmpresa(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            {empresas.map(e => (
              <MenuItem key={e.id_empresa} value={e.id_empresa}>{e.nombre_legal || e.id_empresa}</MenuItem>
            ))}
          </TextField>
          <TextField size="small" placeholder="Usuario" value={filtroUsuario} onChange={e => setFiltroUsuario(e.target.value)} sx={{ minWidth: 120 }} />
          <TextField size="small" placeholder="Tipo evento" value={filtroTipoEvento} onChange={e => setFiltroTipoEvento(e.target.value)} sx={{ minWidth: 120 }} />
          <TextField size="small" placeholder="Módulo" value={filtroModulo} onChange={e => setFiltroModulo(e.target.value)} sx={{ minWidth: 120 }} />
          <TextField size="small" placeholder="Modelo" value={filtroModelo} onChange={e => setFiltroModelo(e.target.value)} sx={{ minWidth: 120 }} />
          <TextField size="small" placeholder="Empresa" value={filtroEmpresa} onChange={e => setFiltroEmpresa(e.target.value)} sx={{ minWidth: 120 }} />
          <TextField size="small" placeholder="Resultado" value={filtroResultado} onChange={e => setFiltroResultado(e.target.value)} sx={{ minWidth: 120 }} />
          <TextField size="small" type="date" value={filtroFechaInicio} onChange={e => setFiltroFechaInicio(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField size="small" type="date" value={filtroFechaFin} onChange={e => setFiltroFechaFin(e.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
      </Box>
      <DataTable
        columns={columns}
        rows={filteredLogs}
        getRowKey={(l) => String(l.id)}
        loading={loading}
        emptyMessage={errorMsg || 'No se encontraron registros.'}
      />
    </PageContainer>
  );
};

export default AuditLogListPage;

import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import {
  aplicarPlantillaRol,
  fetchMatrizRol,
  guardarMatrizRol,
  type AccionRbac,
  type AlcanceRbac,
  type AmbitoRbac,
  type ModuloRbac,
  type PoliticaAccesoItem,
} from '../../services/accessStudio';

interface Props {
  idRol: string;
}

type CellKey = `${string}:${string}`;

function cellKey(modulo: string, accion: string): CellKey {
  return `${modulo}:${accion}`;
}

function defaultPolicy(modulo: ModuloRbac, accion: AccionRbac): PoliticaAccesoItem {
  return {
    modulo,
    accion,
    ambito: 'AMBOS',
    alcance: 'EMPRESA',
    permitido: false,
    campos_ocultos: [],
  };
}

function toPolicyMap(politicas: PoliticaAccesoItem[]): Map<CellKey, PoliticaAccesoItem> {
  const next = new Map<CellKey, PoliticaAccesoItem>();
  for (const pol of politicas) {
    next.set(cellKey(pol.modulo, pol.accion), {
      ...pol,
      campos_ocultos: Array.isArray(pol.campos_ocultos) ? [...pol.campos_ocultos] : [],
    });
  }
  return next;
}

export const AccessStudioMatrix: React.FC<Props> = ({ idRol }) => {
  const queryClient = useQueryClient();
  const [moduloFiltro, setModuloFiltro] = useState<string>('TODOS');
  const [policiesMap, setPoliciesMap] = useState<Map<CellKey, PoliticaAccesoItem>>(() => new Map());
  const [feedback, setFeedback] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['/core/roles/matriz-acceso/', idRol],
    queryFn: () => fetchMatrizRol(idRol),
    enabled: Boolean(idRol),
  });

  useEffect(() => {
    if (!data) return;
    setPoliciesMap(toPolicyMap(data.politicas));
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const politicas = Array.from(policiesMap.values()).filter((p) => p.permitido || p.id_politica);
      return guardarMatrizRol(idRol, {
        id_empresa: data?.id_empresa,
        politicas: politicas.map((p) => ({
          modulo: p.modulo,
          accion: p.accion,
          ambito: p.ambito,
          alcance: p.alcance,
          permitido: p.permitido,
          campos_ocultos: p.campos_ocultos,
        })),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/roles/matriz-acceso/', idRol] });
      setFeedback({ severity: 'success', text: 'Matriz RBAC/ABAC guardada correctamente.' });
    },
    onError: () => {
      setFeedback({ severity: 'error', text: 'Error al guardar la matriz de acceso.' });
    },
  });

  const presetMutation = useMutation({
    mutationFn: (codigoPlantilla: string) => aplicarPlantillaRol(idRol, codigoPlantilla, data?.id_empresa),
    onSuccess: (res) => {
      setPoliciesMap(toPolicyMap(res.politicas));
      queryClient.invalidateQueries({ queryKey: ['/core/roles/matriz-acceso/', idRol] });
      setFeedback({ severity: 'success', text: `Plantilla ${res.codigo_plantilla} aplicada.` });
    },
    onError: () => {
      setFeedback({ severity: 'error', text: 'No se pudo aplicar la plantilla seleccionada.' });
    },
  });

  const modulosVisibles = useMemo(() => {
    if (!data) return [];
    if (moduloFiltro === 'TODOS') return data.catalogo.modulos;
    return data.catalogo.modulos.filter((m) => m.codigo === moduloFiltro);
  }, [data, moduloFiltro]);

  const updatePolicy = (
    modulo: ModuloRbac,
    accion: AccionRbac,
    updater: (prev: PoliticaAccesoItem) => PoliticaAccesoItem,
  ) => {
    const key = cellKey(modulo, accion);
    setPoliciesMap((prev) => {
      const next = new Map(prev);
      const current = next.get(key) ?? defaultPolicy(modulo, accion);
      next.set(key, updater(current));
      return next;
    });
  };

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" py={4}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  if (isError || !data) {
    return <Alert severity="error">No se pudo cargar la matriz RBAC/ABAC del rol.</Alert>;
  }

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} data-testid="access-studio-matrix">
      <Stack spacing={2.5}>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={2}>
          <Box>
            <Typography variant="h6">Access Studio (RBAC / ABAC Granular)</Typography>
            <Typography variant="body2" color="text.secondary">
              Configura permisos por Módulo × Acción × Ámbito (Fiscal / Gerencial) × Alcance y ocultamiento de campos.
            </Typography>
          </Box>
          <Button
            variant="contained"
            data-testid="access-studio-save"
            disabled={saveMutation.isPending || presetMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? 'Guardando...' : 'Guardar matriz'}
          </Button>
        </Stack>

        {feedback && (
          <Alert severity={feedback.severity} onClose={() => setFeedback(null)} data-testid="access-studio-feedback">
            {feedback.text}
          </Alert>
        )}

        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={2}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Typography variant="body2" sx={{ alignSelf: 'center', mr: 1, fontWeight: 600 }}>
              Plantillas:
            </Typography>
            {data.catalogo.plantillas.map((tpl) => (
              <Button
                key={tpl.codigo}
                size="small"
                variant="outlined"
                data-testid={`preset-btn-${tpl.codigo}`}
                disabled={presetMutation.isPending}
                onClick={() => presetMutation.mutate(tpl.codigo)}
              >
                {tpl.nombre}
              </Button>
            ))}
          </Stack>

          <TextField
            select
            size="small"
            label="Filtrar módulo"
            value={moduloFiltro}
            onChange={(e) => setModuloFiltro(e.target.value)}
            sx={{ minWidth: 220 }}
            slotProps={{ htmlInput: { 'data-testid': 'access-studio-module-filter' } }}
          >
            <MenuItem value="TODOS">Todos los módulos</MenuItem>
            {data.catalogo.modulos.map((m) => (
              <MenuItem key={m.codigo} value={m.codigo}>
                {m.etiqueta}
              </MenuItem>
            ))}
          </TextField>
        </Stack>

        <TableContainer component={Box} sx={{ maxHeight: 520, overflowY: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Módulo</TableCell>
                <TableCell>Acción</TableCell>
                <TableCell align="center">Permitido</TableCell>
                <TableCell>Ámbito</TableCell>
                <TableCell>Alcance</TableCell>
                <TableCell>Campos sensibles ocultos</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {modulosVisibles.map((mod) =>
                data.catalogo.acciones.map((acc) => {
                  const modCode = mod.codigo as ModuloRbac;
                  const accCode = acc.codigo as AccionRbac;
                  const policy = policiesMap.get(cellKey(modCode, accCode)) ?? defaultPolicy(modCode, accCode);
                  const camposAplicables = data.catalogo.campos_sensibles;

                  return (
                    <TableRow key={`${modCode}:${accCode}`} hover>
                      <TableCell sx={{ fontWeight: 500 }}>{mod.etiqueta}</TableCell>
                      <TableCell>{acc.etiqueta}</TableCell>
                      <TableCell align="center">
                        <Switch
                          size="small"
                          checked={policy.permitido}
                          data-testid={`toggle-${modCode}-${accCode}`}
                          slotProps={{
                            input: { 'aria-label': `Permitir ${modCode} ${accCode}` },
                          }}
                          onChange={(e) =>
                            updatePolicy(modCode, accCode, (prev) => ({
                              ...prev,
                              permitido: e.target.checked,
                            }))
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Select
                          size="small"
                          value={policy.ambito}
                          disabled={!policy.permitido}
                          SelectDisplayProps={{
                            'data-testid': `ambito-${modCode}-${accCode}`,
                          } as React.HTMLAttributes<HTMLDivElement>}
                          onChange={(e: SelectChangeEvent) =>
                            updatePolicy(modCode, accCode, (prev) => ({
                              ...prev,
                              ambito: e.target.value as AmbitoRbac,
                            }))
                          }
                        >
                          {data.catalogo.ambitos.map((amb) => (
                            <MenuItem key={amb.codigo} value={amb.codigo}>
                              {amb.etiqueta}
                            </MenuItem>
                          ))}
                        </Select>
                      </TableCell>
                      <TableCell>
                        <Select
                          size="small"
                          value={policy.alcance}
                          disabled={!policy.permitido}
                          SelectDisplayProps={{
                            'data-testid': `alcance-${modCode}-${accCode}`,
                          } as React.HTMLAttributes<HTMLDivElement>}
                          onChange={(e: SelectChangeEvent) =>
                            updatePolicy(modCode, accCode, (prev) => ({
                              ...prev,
                              alcance: e.target.value as AlcanceRbac,
                            }))
                          }
                        >
                          {data.catalogo.alcances.map((alc) => (
                            <MenuItem key={alc.codigo} value={alc.codigo}>
                              {alc.etiqueta}
                            </MenuItem>
                          ))}
                        </Select>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {camposAplicables.map((campo) => {
                            const selected = policy.campos_ocultos.includes(campo.codigo);
                            return (
                              <Chip
                                key={campo.codigo}
                                label={campo.etiqueta}
                                size="small"
                                variant={selected ? 'filled' : 'outlined'}
                                color={selected ? 'warning' : 'default'}
                                disabled={!policy.permitido}
                                data-testid={`chip-${modCode}-${accCode}-${campo.codigo}`}
                                onClick={() =>
                                  updatePolicy(modCode, accCode, (prev) => {
                                    const exists = prev.campos_ocultos.includes(campo.codigo);
                                    return {
                                      ...prev,
                                      campos_ocultos: exists
                                        ? prev.campos_ocultos.filter((c) => c !== campo.codigo)
                                        : [...prev.campos_ocultos, campo.codigo],
                                    };
                                  })
                                }
                              />
                            );
                          })}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  );
                }),
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Stack>
    </Paper>
  );
};

export default AccessStudioMatrix;

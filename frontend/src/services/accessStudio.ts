import { get, post, put } from './api';

export type ModuloRbac =
  | 'ventas'
  | 'compras'
  | 'inventario'
  | 'contabilidad'
  | 'finanzas'
  | 'tesoreria'
  | 'fiscal'
  | 'nomina'
  | 'crm'
  | 'despacho'
  | 'core'
  | 'pos';

export type AccionRbac = 'VER' | 'CREAR' | 'EDITAR' | 'ELIMINAR' | 'APROBAR' | 'EXPORTAR' | 'ANULAR';
export type AmbitoRbac = 'FISCAL' | 'GERENCIAL' | 'AMBOS';
export type AlcanceRbac = 'PROPIO' | 'SUCURSAL' | 'ALMACEN' | 'EMPRESA';

export interface PoliticaAccesoItem {
  id_politica?: string;
  id_empresa?: string;
  id_rol?: string;
  modulo: ModuloRbac;
  accion: AccionRbac;
  ambito: AmbitoRbac;
  alcance: AlcanceRbac;
  permitido: boolean;
  campos_ocultos: string[];
}

export interface CatalogoItemRbac {
  codigo: string;
  etiqueta: string;
}

export interface CampoSensibleRbac {
  codigo: string;
  etiqueta: string;
  modulo: string;
}

export interface PlantillaRolRbac {
  codigo: string;
  nombre: string;
  descripcion: string;
  total_politicas: number;
}

export interface CatalogoRbac {
  modulos: CatalogoItemRbac[];
  acciones: CatalogoItemRbac[];
  ambitos: CatalogoItemRbac[];
  alcances: CatalogoItemRbac[];
  campos_sensibles: CampoSensibleRbac[];
  plantillas: PlantillaRolRbac[];
}

export interface MatrizRolResponse {
  id_rol: string;
  nombre_rol: string;
  id_empresa: string;
  politicas: PoliticaAccesoItem[];
  permisos_asignados: string[];
  catalogo: CatalogoRbac;
}

export interface MiMatrizResponse {
  empresa_id: string;
  es_admin_total: boolean;
  tiene_politicas_explicitas: boolean;
  modulos: Record<
    string,
    Record<
      string,
      {
        permitido: boolean;
        ambito: AmbitoRbac;
        alcance: AlcanceRbac;
        campos_ocultos: string[];
      }
    >
  >;
  campos_ocultos: Record<string, string[]>;
}

export interface GuardarMatrizPayload {
  id_empresa?: string;
  politicas: Array<Pick<PoliticaAccesoItem, 'modulo' | 'accion' | 'ambito' | 'alcance' | 'permitido' | 'campos_ocultos'>>;
}

export async function fetchCatalogoRbac(): Promise<CatalogoRbac> {
  return get<CatalogoRbac>('/core/politicas-acceso/catalogo/');
}

export async function fetchMiMatrizRbac(idEmpresa?: string): Promise<MiMatrizResponse> {
  const qs = idEmpresa ? `?id_empresa=${encodeURIComponent(idEmpresa)}` : '';
  return get<MiMatrizResponse>(`/core/politicas-acceso/mi-matriz/${qs}`);
}

export async function fetchMatrizRol(idRol: string, idEmpresa?: string): Promise<MatrizRolResponse> {
  const qs = idEmpresa ? `?id_empresa=${encodeURIComponent(idEmpresa)}` : '';
  return get<MatrizRolResponse>(`/core/roles/${idRol}/matriz-acceso/${qs}`);
}

export async function guardarMatrizRol(
  idRol: string,
  payload: GuardarMatrizPayload,
): Promise<{ id_rol: string; id_empresa: string; politicas: PoliticaAccesoItem[] }> {
  return put<{ id_rol: string; id_empresa: string; politicas: PoliticaAccesoItem[] }>(
    `/core/roles/${idRol}/matriz-acceso/`,
    { ...payload },
  );
}

export async function aplicarPlantillaRol(
  idRol: string,
  codigoPlantilla: string,
  idEmpresa?: string,
): Promise<{ id_rol: string; id_empresa: string; codigo_plantilla: string; politicas: PoliticaAccesoItem[] }> {
  return post<{ id_rol: string; id_empresa: string; codigo_plantilla: string; politicas: PoliticaAccesoItem[] }>(
    `/core/roles/${idRol}/aplicar-plantilla/`,
    {
      codigo_plantilla: codigoPlantilla,
      ...(idEmpresa ? { id_empresa: idEmpresa } : {}),
    },
  );
}

export async function asignarPermisosRol(
  idRol: string,
  permisosIds: string[],
): Promise<{ id_rol: string; permisos_ids: string[] }> {
  return post<{ id_rol: string; permisos_ids: string[] }>(`/core/roles/${idRol}/asignar-permisos/`, {
    permisos_ids: permisosIds,
  });
}

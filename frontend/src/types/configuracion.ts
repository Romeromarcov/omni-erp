// Tipos para el módulo de configuración
export interface TipoDocumento {
  id_tipo_documento: string;
  codigo: string;
  nombre: string;
  descripcion?: string;
  modulo_origen: string;
  es_transaccional: boolean;
  prefijo_correlativo?: string;
  ultimo_correlativo: number;
}

export interface ParametroSistema {
  id_parametro: string;
  id_empresa?: string;
  nombre_parametro: string;
  codigo_parametro: string;
  valor_parametro: string;
  tipo_dato: 'TEXTO' | 'NUMERO' | 'BOOLEANO' | 'FECHA';
  descripcion?: string;
  activo: boolean;
}

export interface CatalogoValor {
  id_catalogo_valor: string;
  codigo_catalogo: string;
  valor: string;
  descripcion?: string;
  orden: number;
  activo: boolean;
}
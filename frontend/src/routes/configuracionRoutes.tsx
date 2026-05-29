import { lazy } from 'react';
import { Route } from 'react-router-dom';

const TipoDocumentoListPage = lazy(() => import('../pages/Configuracion/TiposDocumento/TipoDocumentoListPage'));
const TipoDocumentoDetailPage = lazy(() => import('../pages/Configuracion/TiposDocumento/TipoDocumentoDetailPage'));
const ParametroSistemaListPage = lazy(() => import('../pages/Configuracion/ParametrosSistema/ParametroSistemaListPage'));
const ParametroSistemaDetailPage = lazy(() => import('../pages/Configuracion/ParametrosSistema/ParametroSistemaDetailPage'));
const CatalogoValorListPage = lazy(() => import('../pages/Configuracion/CatalogosValor/CatalogoValorListPage'));
const CatalogoValorDetailPage = lazy(() => import('../pages/Configuracion/CatalogosValor/CatalogoValorDetailPage'));

export function configuracionRoutes() {
  return (
    <>
      <Route path="/configuracion/tipos-documento" element={<TipoDocumentoListPage />} />
      <Route path="/configuracion/tipos-documento/new" element={<TipoDocumentoDetailPage />} />
      <Route path="/configuracion/tipos-documento/:id_tipo_documento" element={<TipoDocumentoDetailPage />} />

      <Route path="/configuracion/parametros-sistema" element={<ParametroSistemaListPage />} />
      <Route path="/configuracion/parametros-sistema/new" element={<ParametroSistemaDetailPage />} />
      <Route path="/configuracion/parametros-sistema/:id_parametro" element={<ParametroSistemaDetailPage />} />

      <Route path="/configuracion/catalogos-valor" element={<CatalogoValorListPage />} />
      <Route path="/configuracion/catalogos-valor/new" element={<CatalogoValorDetailPage />} />
      <Route path="/configuracion/catalogos-valor/:id_catalogo_valor" element={<CatalogoValorDetailPage />} />
    </>
  );
}

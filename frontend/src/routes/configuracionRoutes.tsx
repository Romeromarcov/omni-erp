import { Route } from 'react-router-dom';
import TipoDocumentoListPage from '../pages/Configuracion/TiposDocumento/TipoDocumentoListPage';
import TipoDocumentoDetailPage from '../pages/Configuracion/TiposDocumento/TipoDocumentoDetailPage';
import ParametroSistemaListPage from '../pages/Configuracion/ParametrosSistema/ParametroSistemaListPage';
import ParametroSistemaDetailPage from '../pages/Configuracion/ParametrosSistema/ParametroSistemaDetailPage';
import CatalogoValorListPage from '../pages/Configuracion/CatalogosValor/CatalogoValorListPage';
import CatalogoValorDetailPage from '../pages/Configuracion/CatalogosValor/CatalogoValorDetailPage';

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

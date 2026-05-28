import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useSidebar } from './SidebarContext';
import './SidebarMenu.css';

const SidebarMenu: React.FC = () => {
  const { isCollapsed, isMobile, isOpen, toggleCollapsed, toggleMobile, closeMobile } = useSidebar();
  const { user } = useAuth();
  const empresaId = user?.empresas?.[0]?.id_empresa || '';

  return (
    <>
      {isMobile && (
        <button
          className="mobile-menu-toggle"
          onClick={toggleMobile}
          aria-label="Abrir menú"
        >
          ☰
        </button>
      )}
      {(isOpen || !isMobile) && (
        <aside className={`sidebar-menu${isCollapsed && !isMobile ? ' collapsed' : ''}${isMobile ? ' mobile' : ''}`}>
          <button
            className="sidebar-toggle"
            onClick={isMobile ? closeMobile : toggleCollapsed}
            aria-label={isCollapsed ? 'Expandir menú' : 'Colapsar menú'}
          >
            {isMobile ? '✕' : (isCollapsed ? '▶' : '◀')}
          </button>
          <nav>
            <ul>
              <li><Link to="/dashboard" onClick={isMobile ? closeMobile : undefined} title="Dashboard">Dashboard</Link></li>
              <li>
                <details>
                  <summary title="Empresas">Empresas</summary>
                  <ul style={{ paddingLeft: 16 }}>
                    <li><Link to="/empresas" onClick={isMobile ? closeMobile : undefined} title="Listado de empresas">Listado de empresas</Link></li>
                    <li>
                      <Link to={`/empresas/${empresaId}/sucursales`} onClick={isMobile ? closeMobile : undefined} title="Sucursales">
                        Sucursales
                      </Link>
                    </li>
                    <li>
                      <Link to="/departamentos" onClick={isMobile ? closeMobile : undefined} title="Departamentos">Departamentos</Link>
                    </li>
                  </ul>
                </details>
              </li>
              <li>
                <details>
                  <summary title="Finanzas">Finanzas</summary>
                  <ul style={{ paddingLeft: 16 }}>
                    <li><Link to="/finanzas/monedas" onClick={isMobile ? closeMobile : undefined} title="Monedas">Monedas</Link></li>
                    <li>
                      <details>
                        <summary title="Cajas Virtuales">Cajas Virtuales</summary>
                        <ul style={{ paddingLeft: 16 }}>
                          <li>
                            <Link to={`/empresas/${empresaId}/cajas`} onClick={isMobile ? closeMobile : undefined} title="Listado de Cajas Virtuales">
                              Listado
                            </Link>
                          </li>
                          <li>
                            <Link to="/finanzas/plantillas-maestro" onClick={isMobile ? closeMobile : undefined} title="Plantillas Maestro">
                              Plantillas Maestro
                            </Link>
                          </li>
                          <li>
                            <Link to="/finanzas/overrides-metodos-pago" onClick={isMobile ? closeMobile : undefined} title="Overrides por Sucursal">
                              Overrides por Sucursal
                            </Link>
                          </li>
                        </ul>
                      </details>
                    </li>
                    <li>
                      <Link to="/finanzas/cajas-fisicas" onClick={isMobile ? closeMobile : undefined} title="Cajas">
                        Cajas
                      </Link>
                    </li>
                    <li>
                      <Link to={`/empresas/${empresaId}/cuentas-bancarias`} onClick={isMobile ? closeMobile : undefined} title="Cuentas Bancarias">
                        Cuentas Bancarias
                      </Link>
                    </li>
                    <li>
                      <Link to={`/empresas/${empresaId}/tasas-cambio`} onClick={isMobile ? closeMobile : undefined} title="Tasas de Cambio">
                        Tasas de Cambio
                      </Link>
                    </li>
                    <li>
                      <Link to={`/empresas/${empresaId}/metodos-pago`} onClick={isMobile ? closeMobile : undefined} title="Métodos de Pago">
                        Métodos de Pago
                      </Link>
                    </li>
                    <li>
                      <Link to={`/empresas/${empresaId}/transacciones-financieras`} onClick={isMobile ? closeMobile : undefined} title="Transacciones Financieras">
                        Transacciones Financieras
                      </Link>
                    </li>
                  </ul>
                </details>
              </li>
              <li>
                <details>
                  <summary title="Ventas">Ventas</summary>
                  <ul style={{ paddingLeft: 16 }}>
                    <li><Link to="/ventas/cotizaciones" onClick={isMobile ? closeMobile : undefined} title="Cotizaciones">Cotizaciones</Link></li>
                    <li><Link to="/ventas/pedidos" onClick={isMobile ? closeMobile : undefined} title="Pedidos">Pedidos</Link></li>
                    <li><Link to="/ventas/notas-venta" onClick={isMobile ? closeMobile : undefined} title="Notas de Venta">Notas de Venta</Link></li>
                    <li><Link to="/ventas/notas-credito-venta" onClick={isMobile ? closeMobile : undefined} title="Notas de Crédito">Notas de Crédito</Link></li>
                    <li><Link to="/ventas/notas-credito-fiscal" onClick={isMobile ? closeMobile : undefined} title="Notas de Crédito Fiscal">Notas de Crédito Fiscal</Link></li>
                    <li><Link to="/ventas/devoluciones-venta" onClick={isMobile ? closeMobile : undefined} title="Devoluciones">Devoluciones</Link></li>
                    <li><Link to="/ventas/facturas-fiscales" onClick={isMobile ? closeMobile : undefined} title="Facturas Fiscales">Facturas Fiscales</Link></li>
                  </ul>
                </details>
              </li>
              <li>
                <details>
                  <summary title="Inventario">Inventario</summary>
                  <ul style={{ paddingLeft: 16 }}>
                    <li><Link to="/inventario" onClick={isMobile ? closeMobile : undefined} title="Dashboard Inventario">Dashboard</Link></li>
                    <li><Link to="/inventario/stock" onClick={isMobile ? closeMobile : undefined} title="Stock Actual">Stock Actual</Link></li>
                    <li><Link to="/inventario/ajustes" onClick={isMobile ? closeMobile : undefined} title="Ajuste Manual">Ajuste Manual</Link></li>
                  </ul>
                </details>
              </li>
              <li>
                <details>
                  <summary title="Usuarios">Usuarios</summary>
                  <ul style={{ paddingLeft: 16 }}>
                    <li><Link to={`/empresas/${empresaId}/usuarios`} onClick={isMobile ? closeMobile : undefined} title="Listado de usuarios">Listado de usuarios</Link></li>
                    <li><Link to="/roles" onClick={isMobile ? closeMobile : undefined} title="Roles">Roles</Link></li>
                    <li><Link to="/permisos" onClick={isMobile ? closeMobile : undefined} title="Permisos">Permisos</Link></li>
                    <li><Link to="/auditoria" onClick={isMobile ? closeMobile : undefined} title="Auditoría">Auditoría</Link></li>
                  </ul>
                </details>
              </li>
              <li>
                <details>
                  <summary title="Configuración">Configuración</summary>
                  <ul style={{ paddingLeft: 16 }}>
                    <li><Link to="/configuracion/tipos-documento" onClick={isMobile ? closeMobile : undefined} title="Tipos de Documento">Tipos de Documento</Link></li>
                    <li><Link to="/configuracion/parametros-sistema" onClick={isMobile ? closeMobile : undefined} title="Parámetros del Sistema">Parámetros del Sistema</Link></li>
                    <li><Link to="/configuracion/catalogos-valor" onClick={isMobile ? closeMobile : undefined} title="Catálogos de Valor">Catálogos de Valor</Link></li>
                  </ul>
                </details>
              </li>
            </ul>
          </nav>
        </aside>
      )}
    </>
  );
};

export default SidebarMenu;

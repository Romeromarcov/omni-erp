import type { ReactNode } from 'react';
import SpaceDashboardOutlined from '@mui/icons-material/SpaceDashboardOutlined';
import PointOfSaleOutlined from '@mui/icons-material/PointOfSaleOutlined';
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined';
import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import RequestQuoteOutlined from '@mui/icons-material/RequestQuoteOutlined';
import ReceiptLongOutlined from '@mui/icons-material/ReceiptLongOutlined';
import BusinessOutlined from '@mui/icons-material/BusinessOutlined';
import GroupOutlined from '@mui/icons-material/GroupOutlined';
import SettingsOutlined from '@mui/icons-material/SettingsOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';

export interface NavItem {
  label: string;
  path: string;
}

export interface NavSection {
  id: string;
  label: string;
  icon: ReactNode;
  /** Ruta directa para secciones sin sub-items (p. ej. Dashboard). */
  path?: string;
  items?: NavItem[];
}

/**
 * Fuente única de verdad de la navegación del ERP.
 * Algunas rutas dependen de la empresa activa, por eso se construye con su id.
 */
export function buildNavigation(empresaId: string): NavSection[] {
  const emp = empresaId || '_';
  return [
    {
      id: 'dashboard',
      label: 'Inicio',
      icon: <SpaceDashboardOutlined />,
      path: '/dashboard',
    },
    {
      id: 'ventas',
      label: 'Ventas',
      icon: <PointOfSaleOutlined />,
      items: [
        { label: 'Cotizaciones', path: '/ventas/cotizaciones' },
        { label: 'Pedidos', path: '/ventas/pedidos' },
        { label: 'Notas de Venta', path: '/ventas/notas-venta' },
        { label: 'Notas de Crédito', path: '/ventas/notas-credito-venta' },
        { label: 'Notas de Crédito Fiscal', path: '/ventas/notas-credito-fiscal' },
        { label: 'Devoluciones', path: '/ventas/devoluciones-venta' },
        { label: 'Facturas Fiscales', path: '/ventas/facturas-fiscales' },
      ],
    },
    {
      id: 'inventario',
      label: 'Inventario',
      icon: <Inventory2Outlined />,
      items: [
        { label: 'Dashboard', path: '/inventario' },
        { label: 'Stock Actual', path: '/inventario/stock' },
        { label: 'Ajuste Manual', path: '/inventario/ajustes' },
      ],
    },
    {
      id: 'finanzas',
      label: 'Finanzas',
      icon: <AccountBalanceWalletOutlined />,
      items: [
        { label: 'Monedas', path: '/finanzas/monedas' },
        { label: 'Tasas de Cambio', path: `/empresas/${emp}/tasas-cambio` },
        { label: 'Métodos de Pago', path: `/empresas/${emp}/metodos-pago` },
        { label: 'Cajas Virtuales', path: `/empresas/${emp}/cajas` },
        { label: 'Cajas Físicas', path: '/finanzas/cajas-fisicas' },
        { label: 'Cuentas Bancarias', path: `/empresas/${emp}/cuentas-bancarias` },
        { label: 'Transacciones', path: `/empresas/${emp}/transacciones-financieras` },
        { label: 'Plantillas Maestro', path: '/finanzas/plantillas-maestro' },
        { label: 'Overrides por Sucursal', path: '/finanzas/overrides-metodos-pago' },
      ],
    },
    {
      id: 'cobranza',
      label: 'Cobranza (CxC)',
      icon: <RequestQuoteOutlined />,
      items: [
        { label: 'Dashboard Cartera', path: '/cobranza/dashboard' },
        { label: 'Gestiones', path: '/cobranza/gestiones' },
        { label: 'Acuerdos de Pago', path: '/cobranza/acuerdos' },
        { label: 'Agente IA', path: '/cobranza/agente' },
      ],
    },
    {
      id: 'fiscal',
      label: 'Fiscal',
      icon: <ReceiptLongOutlined />,
      items: [
        { label: 'Configuración', path: '/configuracion/fiscal' },
        { label: 'Libro de Ventas', path: '/fiscal/libro-ventas' },
        { label: 'Libro de Compras', path: '/fiscal/libro-compras' },
      ],
    },
    {
      id: 'empresas',
      label: 'Empresas',
      icon: <BusinessOutlined />,
      items: [
        { label: 'Listado de Empresas', path: '/empresas' },
        { label: 'Sucursales', path: `/empresas/${emp}/sucursales` },
        { label: 'Departamentos', path: '/departamentos' },
      ],
    },
    {
      id: 'usuarios',
      label: 'Usuarios',
      icon: <GroupOutlined />,
      items: [
        { label: 'Listado de Usuarios', path: `/empresas/${emp}/usuarios` },
        { label: 'Roles', path: '/roles' },
        { label: 'Permisos', path: '/permisos' },
        { label: 'Auditoría', path: '/auditoria' },
      ],
    },
    {
      id: 'configuracion',
      label: 'Configuración',
      icon: <SettingsOutlined />,
      items: [
        { label: 'Tipos de Documento', path: '/configuracion/tipos-documento' },
        { label: 'Parámetros del Sistema', path: '/configuracion/parametros-sistema' },
        { label: 'Catálogos de Valor', path: '/configuracion/catalogos-valor' },
      ],
    },
    {
      id: 'integraciones',
      label: 'Integraciones',
      icon: <HubOutlined />,
      items: [{ label: 'Hub de Integraciones', path: '/integraciones' }],
    },
  ];
}

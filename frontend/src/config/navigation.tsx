import type { ReactNode } from 'react';
import SpaceDashboardOutlined from '@mui/icons-material/SpaceDashboardOutlined';
import PointOfSaleOutlined from '@mui/icons-material/PointOfSaleOutlined';
import PeopleAltOutlined from '@mui/icons-material/PeopleAltOutlined';
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined';
import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import PrecisionManufacturingOutlined from '@mui/icons-material/PrecisionManufacturingOutlined';
import CalculateOutlined from '@mui/icons-material/CalculateOutlined';
import ShoppingCartOutlined from '@mui/icons-material/ShoppingCartOutlined';
import LocalShippingOutlined from '@mui/icons-material/LocalShippingOutlined';
import PaymentsOutlined from '@mui/icons-material/PaymentsOutlined';
import RequestQuoteOutlined from '@mui/icons-material/RequestQuoteOutlined';
import MenuBookOutlined from '@mui/icons-material/MenuBookOutlined';
import SavingsOutlined from '@mui/icons-material/SavingsOutlined';
import AccountBalanceOutlined from '@mui/icons-material/AccountBalanceOutlined';
import ReceiptLongOutlined from '@mui/icons-material/ReceiptLongOutlined';
import BadgeOutlined from '@mui/icons-material/BadgeOutlined';
import FingerprintOutlined from '@mui/icons-material/FingerprintOutlined';
import BusinessOutlined from '@mui/icons-material/BusinessOutlined';
import GroupOutlined from '@mui/icons-material/GroupOutlined';
import SettingsOutlined from '@mui/icons-material/SettingsOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';
import CloudUploadOutlined from '@mui/icons-material/CloudUploadOutlined';
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined';
import AppsOutlined from '@mui/icons-material/AppsOutlined';
import WorkspacePremiumOutlined from '@mui/icons-material/WorkspacePremiumOutlined';
import SupportAgentOutlined from '@mui/icons-material/SupportAgentOutlined';
import FactCheckOutlined from '@mui/icons-material/FactCheckOutlined';
import FolderOutlined from '@mui/icons-material/FolderOutlined';
import NotificationsOutlined from '@mui/icons-material/NotificationsOutlined';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import { isModuleEnabled } from './appProfile';

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

export interface NavOptions {
  /** Si el usuario es el dueño del software (Omni), se muestra el Panel SaaS. */
  esSuperusuarioOmni?: boolean;
}

/**
 * Fuente única de verdad de la navegación del ERP.
 * Algunas rutas dependen de la empresa activa, por eso se construye con su id.
 * El Panel SaaS solo se incluye para el proveedor (es_superusuario_omni).
 */
export function buildNavigation(empresaId: string, options: NavOptions = {}): NavSection[] {
  const emp = empresaId || '_';
  const sections: NavSection[] = [
    {
      id: 'inicio',
      label: 'Aplicaciones',
      icon: <AppsOutlined />,
      path: '/inicio',
    },
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
      id: 'crm',
      label: 'Clientes (CRM)',
      icon: <PeopleAltOutlined />,
      items: [{ label: 'Clientes', path: '/crm/clientes' }],
    },
    {
      id: 'servicio-cliente',
      label: 'Servicio al Cliente',
      icon: <SupportAgentOutlined />,
      items: [
        { label: 'Tickets', path: '/servicio-cliente/tickets' },
        { label: 'Categorías', path: '/servicio-cliente/categorias' },
        { label: 'Base de Conocimiento', path: '/servicio-cliente/base-conocimiento' },
        { label: 'Feedback', path: '/servicio-cliente/feedback' },
      ],
    },
    {
      id: 'escaner',
      label: 'Escáner',
      icon: <QrCodeScannerOutlined />,
      path: '/escaner',
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
      id: 'despacho',
      label: 'Despacho',
      icon: <LocalShippingOutlined />,
      items: [{ label: 'Despachos', path: '/despacho' }],
    },
    {
      id: 'manufactura',
      label: 'Manufactura',
      icon: <PrecisionManufacturingOutlined />,
      items: [{ label: 'Órdenes de Producción', path: '/manufactura/ordenes' }],
    },
    {
      id: 'costos',
      label: 'Costos',
      icon: <CalculateOutlined />,
      items: [{ label: 'Costeo de Producción', path: '/costos' }],
    },
    {
      id: 'compras',
      label: 'Compras',
      icon: <ShoppingCartOutlined />,
      items: [
        { label: 'Órdenes de Compra', path: '/compras/ordenes' },
        { label: 'Cuentas por Pagar', path: '/compras/cuentas-por-pagar' },
      ],
    },
    {
      id: 'proveedores',
      label: 'Proveedores',
      icon: <LocalShippingOutlined />,
      items: [{ label: 'Proveedores', path: '/proveedores/proveedores' }],
    },
    {
      id: 'gastos',
      label: 'Gastos',
      icon: <PaymentsOutlined />,
      items: [
        { label: 'Gastos', path: '/gastos' },
        { label: 'Categorías', path: '/gastos/categorias' },
        { label: 'Reembolsos', path: '/gastos/reembolsos' },
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
      id: 'contabilidad',
      label: 'Contabilidad',
      icon: <MenuBookOutlined />,
      items: [
        { label: 'Plan de Cuentas', path: '/contabilidad/plan-cuentas' },
        { label: 'Asientos Contables', path: '/contabilidad/asientos' },
        { label: 'Mapeos Contables', path: '/contabilidad/mapeos' },
      ],
    },
    {
      id: 'tesoreria',
      label: 'Tesorería',
      icon: <SavingsOutlined />,
      items: [
        { label: 'Movimientos Bancarios', path: '/tesoreria/movimientos-bancarios' },
        { label: 'Conciliación Bancaria', path: '/tesoreria/conciliaciones' },
        { label: 'Cambio de Divisa', path: '/tesoreria/cambio-divisa' },
      ],
    },
    {
      id: 'banca-electronica',
      label: 'Banca Electrónica',
      icon: <AccountBalanceOutlined />,
      items: [{ label: 'Cuentas Bancarias', path: '/banca-electronica' }],
    },
    {
      id: 'cobranza',
      label: 'Cobranza (CxC)',
      icon: <RequestQuoteOutlined />,
      items: [
        { label: 'Dashboard Cartera', path: '/cobranza/dashboard' },
        { label: 'Cuentas por Cobrar', path: '/cobranza/cuentas' },
        { label: 'Gestiones', path: '/cobranza/gestiones' },
        { label: 'Acuerdos de Pago', path: '/cobranza/acuerdos' },
        { label: 'Agente IA', path: '/cobranza/agente' },
      ],
    },
    {
      id: 'rrhh',
      label: 'RRHH',
      icon: <BadgeOutlined />,
      items: [
        { label: 'Empleados', path: '/rrhh/empleados' },
        { label: 'Nómina', path: '/nomina/procesos' },
      ],
    },
    {
      id: 'control-asistencia',
      label: 'Control de Asistencia',
      icon: <FingerprintOutlined />,
      items: [{ label: 'Asistencia', path: '/control-asistencia' }],
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
      id: 'gestion-aprobaciones',
      label: 'Aprobaciones',
      icon: <FactCheckOutlined />,
      items: [
        { label: 'Solicitudes', path: '/aprobaciones/solicitudes' },
        { label: 'Configuración', path: '/aprobaciones/configuracion' },
      ],
    },
    {
      id: 'gestion-documental',
      label: 'Documentos',
      icon: <FolderOutlined />,
      items: [{ label: 'Documentos', path: '/gestion-documental/documentos' }],
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
    {
      id: 'migracion-datos',
      label: 'Migración de Datos',
      icon: <CloudUploadOutlined />,
      items: [{ label: 'Migración de Datos', path: '/migracion-datos' }],
    },
    {
      id: 'notificaciones',
      label: 'Notificaciones',
      icon: <NotificationsOutlined />,
      path: '/notificaciones',
    },
    {
      id: 'agentes',
      label: 'Agentes IA',
      icon: <AutoAwesomeOutlined />,
      path: '/agentes',
    },
  ];

  if (options.esSuperusuarioOmni) {
    sections.push({
      id: 'admin-saas',
      label: 'Panel SaaS',
      icon: <WorkspacePremiumOutlined />,
      items: [
        { label: 'Dashboard', path: '/admin-saas' },
        { label: 'Tenants', path: '/admin-saas/tenants' },
        { label: 'Planes', path: '/admin-saas/planes' },
        { label: 'Suscripciones', path: '/admin-saas/suscripciones' },
        { label: 'Proveedores de integración', path: '/admin-saas/proveedores' },
      ],
    });
  }

  // Perfil de build (D4): el standalone de cobranza oculta los módulos no
  // imprescindibles (ventas, inventario, fiscal, escáner). En 'full' pasa todo.
  return sections.filter((s) => isModuleEnabled(s.id));
}

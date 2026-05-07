from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views_extra.tasa_oficial_bcv import TasaCambioOficialBCVView
from .views import MonedaViewSet, TasaCambioViewSet, MetodoPagoViewSet, \
    TransaccionFinancieraViewSet, \
    MovimientoCajaBancoViewSet, CajaViewSet, CajaFisicaViewSet, CuentaBancariaEmpresaViewSet, MonedaEmpresaActivaViewSet, MetodoPagoEmpresaActivaViewSet, DatafonoViewSet, TransaccionDatafonoViewSet, SesionDatafonoViewSet, DepositoDatafonoViewSet, CajaUsuarioViewSet, CajaVirtualUsuarioViewSet, CajaFisicaUsuarioViewSet, PlantillaMaestroCajasVirtualesViewSet, CajaVirtualAutoViewSet, CajaMetodoPagoOverrideViewSet, SesionCajaFisicaViewSet, PagoViewSet
from .views_ajustes import AjusteCajaBancoViewSet

router = DefaultRouter()
router.register(r'monedas', MonedaViewSet)
router.register(r'tasas-cambio', TasaCambioViewSet)
router.register(r'metodos-pago', MetodoPagoViewSet)
router.register(r'transacciones-financieras', TransaccionFinancieraViewSet)
router.register(r'movimientos-caja-banco', MovimientoCajaBancoViewSet)
router.register(r'cajas', CajaViewSet)
router.register(r'cajas-fisicas', CajaFisicaViewSet)
router.register(r'cuentas-bancarias-empresa', CuentaBancariaEmpresaViewSet)
router.register(r'monedas-empresa-activas', MonedaEmpresaActivaViewSet)
router.register(r'metodos-pago-empresa-activas', MetodoPagoEmpresaActivaViewSet, basename='metodos-pago-empresa-activas')
router.register(r'ajustes-caja-banco', AjusteCajaBancoViewSet, basename='ajustes-caja-banco')
router.register(r'datafono', DatafonoViewSet, basename='datafono')
router.register(r'transacciones-datafono', TransaccionDatafonoViewSet)
router.register(r'sesiones-datafono', SesionDatafonoViewSet)
router.register(r'depositos-datafono', DepositoDatafonoViewSet)
router.register(r'cajas-usuario', CajaVirtualUsuarioViewSet, basename='cajas-usuario')
router.register(r'cajas-fisicas-usuario', CajaFisicaUsuarioViewSet)
router.register(r'plantillas-maestro-cajas', PlantillaMaestroCajasVirtualesViewSet)
router.register(r'cajas-virtuales-auto', CajaVirtualAutoViewSet)
router.register(r'overrides-metodos-pago', CajaMetodoPagoOverrideViewSet)
router.register(r'sesiones-caja', SesionCajaFisicaViewSet)
router.register(r'pagos', PagoViewSet)

# Aliases for frontend compatibility
router.register(r'cuentas-bancarias', CuentaBancariaEmpresaViewSet, basename='cuentas-bancarias')
router.register(r'datafonos', DatafonoViewSet, basename='datafonos')



urlpatterns = [
    path('', include(router.urls)),
    path('tasa-oficial-bcv/', TasaCambioOficialBCVView.as_view(), name='tasa-oficial-bcv'),
]

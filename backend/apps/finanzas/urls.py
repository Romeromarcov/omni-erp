from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CajaFisicaUsuarioViewSet,
    CajaFisicaViewSet,
    CajaMetodoPagoOverrideViewSet,
    CajaUsuarioViewSet,
    CajaViewSet,
    CajaVirtualAutoViewSet,
    CajaVirtualUsuarioViewSet,
    CuentaBancariaEmpresaViewSet,
    DatafonoViewSet,
    DepositoDatafonoViewSet,
    MetodoPagoEmpresaActivaViewSet,
    MetodoPagoViewSet,
    MonedaEmpresaActivaViewSet,
    MonedaViewSet,
    MovimientoCajaBancoViewSet,
    PagoViewSet,
    PlantillaMaestroCajasVirtualesViewSet,
    SesionCajaFisicaViewSet,
    SesionDatafonoViewSet,
    TasaCambioViewSet,
    TransaccionDatafonoViewSet,
    TransaccionFinancieraViewSet,
)
from .views_ajustes import AjusteCajaBancoViewSet
from .views_extra.tasa_oficial_bcv import TasaCambioOficialBCVView
from .views_pagos_terceros import PagoTerceroViewSet

router = DefaultRouter()
router.register(r"monedas", MonedaViewSet)
router.register(r"tasas-cambio", TasaCambioViewSet)
router.register(r"metodos-pago", MetodoPagoViewSet)
router.register(r"transacciones-financieras", TransaccionFinancieraViewSet)
router.register(r"movimientos-caja-banco", MovimientoCajaBancoViewSet)
router.register(r"cajas", CajaViewSet)
router.register(r"cajas-fisicas", CajaFisicaViewSet)
router.register(r"cuentas-bancarias-empresa", CuentaBancariaEmpresaViewSet)
router.register(r"monedas-empresa-activas", MonedaEmpresaActivaViewSet)
router.register(
    r"metodos-pago-empresa-activas", MetodoPagoEmpresaActivaViewSet, basename="metodos-pago-empresa-activas"
)
router.register(r"ajustes-caja-banco", AjusteCajaBancoViewSet, basename="ajustes-caja-banco")
router.register(r"datafono", DatafonoViewSet, basename="datafono")
router.register(r"transacciones-datafono", TransaccionDatafonoViewSet)
router.register(r"sesiones-datafono", SesionDatafonoViewSet)
router.register(r"depositos-datafono", DepositoDatafonoViewSet)
router.register(r"cajas-usuario", CajaVirtualUsuarioViewSet, basename="cajas-usuario")
router.register(r"cajas-fisicas-usuario", CajaFisicaUsuarioViewSet)
router.register(r"plantillas-maestro-cajas", PlantillaMaestroCajasVirtualesViewSet)
router.register(r"cajas-virtuales-auto", CajaVirtualAutoViewSet)
router.register(r"overrides-metodos-pago", CajaMetodoPagoOverrideViewSet)
router.register(r"sesiones-caja", SesionCajaFisicaViewSet)
router.register(r"pagos", PagoViewSet)
router.register(r"pagos-terceros", PagoTerceroViewSet)

# Aliases for frontend compatibility
router.register(r"cuentas-bancarias", CuentaBancariaEmpresaViewSet, basename="cuentas-bancarias")
router.register(r"datafonos", DatafonoViewSet, basename="datafonos")


urlpatterns = [
    path("", include(router.urls)),
    path("tasa-oficial-bcv/", TasaCambioOficialBCVView.as_view(), name="tasa-oficial-bcv"),
]

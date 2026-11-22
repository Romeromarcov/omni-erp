import logging
import uuid
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.throttling import EscrituraRateThrottle

from django.db import models
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers_conciliacion_pagos import (
    AsignacionPagoSerializer,
    ConciliarDocumentosInputSerializer,
    ConciliarDocumentosResponseSerializer,
    SugerirDistribucionResponseSerializer,
)

logger = logging.getLogger(__name__)

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import IdempotentCreateMixin, idempotent
from apps.core.viewsets import BaseModelViewSet, NulSafeFilterMixin, get_empresas_visible, validar_uuid_param
from apps.tesoreria.serializers import CajaSerializer

from .models import (
    Caja,
    CajaFisica,
    CajaFisicaUsuario,
    CajaMetodoPagoOverride,
    CajaUsuario,
    CajaVirtualAuto,
    CajaVirtualUsuario,
    Datafono,
    DepositoDatafono,
    Pago,
    PlantillaMaestroCajasVirtuales,
    SesionCajaFisica,
    SesionDatafono,
    TransaccionDatafono,
)
from .serializers import (
    CajaFisicaSerializer,
    CajaFisicaUsuarioSerializer,
    CajaMetodoPagoOverrideSerializer,
    CajaUsuarioSerializer,
    CajaVirtualAutoSerializer,
    CajaVirtualUsuarioSerializer,
    DatafonoSerializer,
    DepositoDatafonoSerializer,
    PagoSerializer,
    PlantillaMaestroCajasVirtualesSerializer,
    SesionCajaFisicaSerializer,
    SesionDatafonoSerializer,
    TransaccionDatafonoSerializer,
)


class SesionCajaFisicaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = SesionCajaFisica.objects.all()
    serializer_class = SesionCajaFisicaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        from apps.core.viewsets import get_empresas_visible

        return SesionCajaFisica.objects.filter(empresa__in=get_empresas_visible(self.request.user)).select_related(
            "usuario", "caja_fisica", "sucursal", "empresa"
        )

    def perform_create(self, serializer):
        """
        Abre una sesión de caja física vía POST /sesiones-caja/.

        FIX (bugs lote 3): este método estaba roto de punta a punta —
        (a) buscaba ``Caja`` (virtual) con el campo inexistente ``es_fisica``
        → FieldError 500 en TODO POST; (b) llamaba ``abrir_sesion`` con kwargs
        que la firma no acepta (``observaciones``,
        ``cargar_plantillas_predeterminadas``) → TypeError; (c) invocaba
        ``instance.cargar_plantillas_predeterminadas()``, método que el modelo
        no define → AttributeError; (d) la búsqueda no estaba acotada al
        tenant (R-CODE-1). Ahora resuelve la ``CajaFisica`` real escopeada a
        las empresas visibles del usuario y delega en
        ``SesionCajaFisica.abrir_sesion`` (misma lógica que el endpoint
        ``cajas-fisicas/{id}/abrir-sesion/``).
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.core.viewsets import get_empresas_visible

        caja_fisica_id = self.request.data.get("caja_fisica_principal")
        if not caja_fisica_id:
            raise serializers.ValidationError(
                {"caja_fisica_principal": "Debe especificar la caja física para abrir la sesión"}
            )

        try:
            caja_fisica = CajaFisica.objects.filter(empresa__in=get_empresas_visible(self.request.user)).get(
                id_caja_fisica=caja_fisica_id, activa=True
            )
        except (CajaFisica.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            # R-CODE-1: mismo mensaje para inexistente, inactiva, malformada o
            # ajena — no se filtra existencia de cajas de otros tenants.
            raise serializers.ValidationError({"caja_fisica_principal": "Caja física no encontrada o no válida"})

        try:
            instance = SesionCajaFisica.abrir_sesion(
                caja_fisica=caja_fisica,
                usuario=self.request.user,
                ip_address=self.request.META.get("REMOTE_ADDR"),
                user_agent=(self.request.META.get("HTTP_USER_AGENT") or "")[:1000] or None,
            )
        except ValueError as exc:
            # Carrera de doble apertura (bugs lote 4): el perdedor del INSERT
            # concurrente recibe un 400 de negocio, no un 500.
            raise serializers.ValidationError({"detail": str(exc)})
        observaciones = self.request.data.get("observaciones")
        if observaciones:
            instance.notas = observaciones
            instance.save(update_fields=["notas"])
        # La creación no pasa por serializer.save(); enlazar la instancia para
        # que la respuesta 201 devuelva la sesión real (id_sesion incluido).
        serializer.instance = instance

    @action(detail=True, methods=["post"], url_path="cerrar")
    def cerrar_sesion(self, request, pk=None):
        """
        Cierra la sesión de caja: realiza el cierre de las cajas indicadas en
        ``saldos_reales`` ({id_caja: saldo real contado} — la caja física de
        la sesión y/o sus cajas virtuales) y marca la sesión CERRADA, todo en
        una sola transacción. Retorna la sesión y el reporte de cierres.

        FIX (endpoint roto): llamaba ``sesion.cerrar_sesion(saldos_reales=...)``
        con una firma del modelo que solo aceptaba ``notas_cierre`` →
        TypeError 500 en toda invocación.
        """
        from django.utils.dateparse import parse_datetime

        sesion = self.get_object()
        saldos_reales = request.data.get("saldos_reales") or {}
        if not isinstance(saldos_reales, dict):
            return Response({"error": "saldos_reales debe ser un objeto {id_caja: saldo_real}."}, status=400)
        hasta = request.data.get("hasta")
        hasta_dt = parse_datetime(hasta) if hasta else None
        if hasta and hasta_dt is None:
            return Response({"error": "El parámetro 'hasta' no tiene un formato de fecha/hora válido."}, status=400)
        usuario = request.user if request.user.is_authenticated else None
        try:
            resultados = sesion.cerrar_sesion(
                notas_cierre=request.data.get("notas_cierre"),
                saldos_reales=saldos_reales,
                usuario=usuario,
                hasta=hasta_dt,
            )
        except ValueError as exc:
            # Mensajes de negocio controlados (sesión cerrada, caja ajena,
            # saldo inválido); no se expone ningún detalle interno.
            return domain_error_response(exc, status_code=400)
        except Exception:
            logger.exception("Error al cerrar sesión de caja")
            return Response({"error": "No se pudo cerrar la sesión. Intente de nuevo."}, status=400)
        sesion.refresh_from_db()
        return Response({"sesion": SesionCajaFisicaSerializer(sesion).data, "cierres": resultados})

    @action(detail=True, methods=["post"], url_path="transferir-entre-cajas")
    def transferir_entre_cajas(self, request, pk=None):
        """
        Transfiere saldo entre dos cajas virtuales de la sesión (las asociadas
        a la caja física de la sesión), p. ej. registradora → gerencia.

        FIX (CTF-015.1): hacía ``sesion.cajas.get(...)`` pero
        ``SesionCajaFisica`` no tiene relación ``cajas`` (la real es
        ``caja_fisica.cajas_virtuales``); el AttributeError caía en un
        ``except Exception`` y el endpoint respondía 400 SIEMPRE — código
        muerto que aparentaba validación. Ahora la transferencia ocurre de
        verdad y solo errores esperables se traducen a 400.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        sesion = self.get_object()
        caja_origen_id = request.data.get("caja_origen")
        caja_destino_id = request.data.get("caja_destino")
        monto = request.data.get("monto")
        usuario = request.user if request.user.is_authenticated else None
        # FIX (bugs lote 4): monto se valida como AUSENTE solo si es None o
        # string en blanco — un 0 numérico (falsy) debe llegar a la validación
        # de negocio y responder "mayor a cero", no el mensaje genérico.
        monto_ausente = monto is None or (isinstance(monto, str) and not monto.strip())
        if not (caja_origen_id and caja_destino_id) or monto_ausente:
            return Response({"error": "Debe indicar caja_origen, caja_destino y monto."}, status=400)
        cajas_de_sesion = sesion.caja_fisica.cajas_virtuales
        try:
            caja_origen = cajas_de_sesion.get(id_caja=caja_origen_id)
            caja_destino = cajas_de_sesion.get(id_caja=caja_destino_id)
        except (Caja.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            # R-CODE-1: mismo mensaje para caja inexistente, malformada o de
            # otra sesión/tenant — no se filtra existencia de cajas ajenas.
            return Response({"error": "Caja origen o destino no pertenece a la sesión."}, status=400)
        if not caja_origen.activa or not caja_destino.activa:
            # Las cajas resueltas ya pertenecen a la sesión (mismo tenant), así
            # que el mensaje específico no filtra existencia ajena (R-CODE-1).
            # Transferir desde/hacia una caja desactivada movería saldo a una
            # caja fuera de operación (invisible en cierres y libro por defecto).
            return Response(
                {"error": "No se puede transferir desde o hacia una caja virtual desactivada."},
                status=400,
            )
        try:
            mov_salida, mov_entrada = transferencia_entre_cajas(caja_origen, caja_destino, monto, usuario=usuario)
        except ValueError as exc:
            # Mensajes de negocio controlados (monto, saldo, moneda); no se
            # expone ningún detalle interno.
            return domain_error_response(exc, status_code=400)
        return Response(
            {
                "movimiento_salida_id": mov_salida.id_movimiento,
                "movimiento_entrada_id": mov_entrada.id_movimiento,
                "caja_origen": str(caja_origen),
                "caja_destino": str(caja_destino),
                # R-CODE-4: monto efectivamente movido (Decimal), no eco crudo.
                "monto": str(mov_salida.monto),
            }
        )


from rest_framework.decorators import action


# NOTA: existía aquí una clase DatafonoViewSet duplicada (muerta, sombreada por
# la definición posterior en este mismo módulo). Se eliminó en el plan "cero
# dudas" para evitar confusión; el ViewSet efectivo y endurecido (R-CODE-1) está
# más abajo.


# ViewSet para MetodoPagoEmpresaActiva
from rest_framework import permissions, viewsets

from .models import MetodoPagoEmpresaActiva
from .serializers import MetodoPagoEmpresaActivaSerializer


class MetodoPagoEmpresaActivaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = MetodoPagoEmpresaActiva.objects.all()
    serializer_class = MetodoPagoEmpresaActivaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from apps.core.viewsets import get_empresas_visible

        # R-CODE-1: SIEMPRE acotar al tenant; los query params solo estrechan
        # (antes filtraban opcionalmente → fuga cross-tenant sin ?empresa=).
        qs = MetodoPagoEmpresaActiva.objects.filter(
            empresa__in=get_empresas_visible(self.request.user)
        ).select_related("metodo_pago", "empresa")
        empresa = self.request.query_params.get("empresa")
        metodo_pago = self.request.query_params.get("metodo_pago")
        if empresa:
            qs = qs.filter(empresa=empresa)
        if metodo_pago:
            qs = qs.filter(metodo_pago=metodo_pago)
        return qs


from rest_framework import permissions, viewsets


from .models import (
    CuentaBancariaEmpresa,
    MetodoPago,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    TasaCambio,
    TipoTasaCambio,
    TransaccionFinanciera,
)
from .serializers import (
    CuentaBancariaEmpresaSerializer,
    EquivalenciasTrimonetariasInputSerializer,
    MetodoPagoSerializer,
    MonedaEmpresaActivaSerializer,
    MonedaSerializer,
    MovimientoCajaBancoSerializer,
    TasaCambioSerializer,
    TipoTasaCambioSerializer,
    TransaccionFinancieraSerializer,
)


class _CatalogoTenantGuardMixin:
    """Restringe escritura/borrado de catálogos híbridos (globales o públicos) a superusuario/dueño."""

    _guard_empresa_field: str = "empresa"
    _guard_global_flags: tuple[str, ...] = ()
    _guard_recurso_nombre: str = "registros"
    _guard_auto_empresa_en_create: bool = False

    def _assert_puede_escribir_catalogo(self, instance=None, data=None, prevalidate_post=False, is_create=False):
        user = self.request.user
        if getattr(user, "es_superusuario_omni", False):
            return
        from rest_framework.exceptions import PermissionDenied

        emp_field = self._guard_empresa_field
        visible_ids = set(get_empresas_visible(user).values_list("id_empresa", flat=True))

        if instance is not None:
            is_flagged = any(bool(getattr(instance, f, False)) for f in self._guard_global_flags)
            inst_emp_id = getattr(instance, f"{emp_field}_id", None)
            if is_flagged or inst_emp_id is None or inst_emp_id not in visible_ids:
                raise PermissionDenied(
                    f"No tiene permiso para modificar o eliminar {self._guard_recurso_nombre} globales, públicos o de otra empresa."
                )

        if data is not None:
            is_flagged = any(
                data.get(f, getattr(instance, f, False) if instance else False) in (True, "true", "True", "1", 1)
                for f in self._guard_global_flags
            )
            if is_flagged:
                raise PermissionDenied(
                    f"Solo un superusuario Omni puede crear o marcar {self._guard_recurso_nombre} globales o públicos."
                )
            if prevalidate_post:
                if emp_field in data and data.get(emp_field) is None:
                    raise PermissionDenied(
                        f"Solo un superusuario Omni puede crear {self._guard_recurso_nombre} globales."
                    )
                if is_create and self._guard_auto_empresa_en_create and not visible_ids:
                    raise PermissionDenied(
                        f"El usuario no tiene una empresa visible para crear {self._guard_recurso_nombre}."
                    )
                return

            if is_create and self._guard_auto_empresa_en_create:
                if not visible_ids:
                    raise PermissionDenied(
                        f"El usuario no tiene una empresa visible para crear {self._guard_recurso_nombre}."
                    )
                if emp_field in data:
                    raw_emp = data.get(emp_field)
                    emp_id = getattr(raw_emp, "pk", raw_emp)
                    if emp_id is None or emp_id not in visible_ids:
                        raise PermissionDenied(
                            f"No tiene permiso para asignar {self._guard_recurso_nombre} fuera de su empresa."
                        )
                return

            default_emp = getattr(instance, f"{emp_field}_id", None) if instance else None
            raw_emp = data.get(emp_field, default_emp)
            emp_id = getattr(raw_emp, "pk", raw_emp)
            if emp_id is None or emp_id not in visible_ids:
                raise PermissionDenied(
                    f"Solo un superusuario Omni puede crear o asignar {self._guard_recurso_nombre} globales o de otra empresa."
                )

    def check_permissions(self, request):
        super().check_permissions(request)
        if getattr(self, "action", None) == "create" and hasattr(request, "data"):
            self._assert_puede_escribir_catalogo(data=request.data, prevalidate_post=True, is_create=True)

    def check_object_permissions(self, request, obj):
        from rest_framework.permissions import SAFE_METHODS

        super().check_object_permissions(request, obj)
        if request.method not in SAFE_METHODS and getattr(self, "action", None) in (
            None,
            "update",
            "partial_update",
            "destroy",
        ):
            data = request.data if request.method in ("PUT", "PATCH") and hasattr(request, "data") else None
            self._assert_puede_escribir_catalogo(instance=obj, data=data, prevalidate_post=True)

    def perform_create(self, serializer):
        self._assert_puede_escribir_catalogo(data=serializer.validated_data, is_create=True)
        serializer.save()

    def perform_update(self, serializer):
        self._assert_puede_escribir_catalogo(instance=serializer.instance, data=serializer.validated_data)
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_puede_escribir_catalogo(instance=instance)
        instance.delete()


class MonedaViewSet(_CatalogoTenantGuardMixin, BaseModelViewSet):
    _guard_empresa_field = "empresa"
    _guard_global_flags = ("es_generica", "es_publica")
    _guard_recurso_nombre = "monedas"
    _guard_auto_empresa_en_create = True

    @action(detail=False, methods=["get"], url_path="activas")
    def activas(self, request):
        user = request.user
        if getattr(user, "es_superusuario_omni", False):
            queryset = Moneda.objects.all()
        else:
            empresas_usuario = get_empresas_visible(user)
            monedas_visibles = Moneda.objects.filter(
                models.Q(es_generica=True) | models.Q(es_publica=True) | models.Q(empresa__in=empresas_usuario)
            ).distinct()
            if not empresas_usuario.exists():
                queryset = monedas_visibles
            else:
                from .cache import obtener_monedas_activas_ids

                empresa = empresas_usuario.first()
                activas_ids = set(obtener_monedas_activas_ids(empresa.pk))
                queryset = monedas_visibles.filter(id_moneda__in=activas_ids)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    queryset = Moneda.objects.all()
    serializer_class = MonedaSerializer

    def get_queryset(self):
        user = self.request.user
        # Superusuario Omni ERP ve todas
        if getattr(user, "es_superusuario_omni", False):
            return Moneda.objects.all()
        empresas_usuario = get_empresas_visible(user)
        # Monedas visibles (genéricas, públicas, propias)
        monedas_visibles = Moneda.objects.filter(
            models.Q(es_generica=True) | models.Q(es_publica=True) | models.Q(empresa__in=empresas_usuario)
        ).distinct()
        return monedas_visibles


class TipoTasaCambioViewSet(_CatalogoTenantGuardMixin, BaseModelViewSet):
    _guard_empresa_field = "id_empresa"
    _guard_global_flags = ()
    _guard_recurso_nombre = "tipos de tasa de cambio"
    _guard_auto_empresa_en_create = True
    queryset = TipoTasaCambio.objects.all()
    serializer_class = TipoTasaCambioSerializer
    search_fields = ["codigo", "nombre", "descripcion"]

    def get_queryset(self):
        from django.db.models import Q

        user = self.request.user
        if getattr(user, "es_superusuario_omni", False):
            return TipoTasaCambio.objects.all().order_by("prioridad", "codigo")
        return TipoTasaCambio.objects.filter(
            Q(id_empresa__isnull=True) | Q(id_empresa__in=get_empresas_visible(user))
        ).order_by("prioridad", "codigo")


class TasaCambioViewSet(_CatalogoTenantGuardMixin, BaseModelViewSet):
    _guard_empresa_field = "id_empresa"
    _guard_global_flags = ()
    _guard_recurso_nombre = "tasas de cambio"
    queryset = TasaCambio.objects.all()
    serializer_class = TasaCambioSerializer

    def get_queryset(self):
        # R-CODE-1: tasas globales (BCV) son visibles para todos (id_empresa nulo),
        # las específicas se filtran por empresa visible del usuario.
        from django.db.models import Q
        from apps.core.viewsets import get_empresas_visible

        return TasaCambio.objects.filter(
            Q(id_empresa__isnull=True) | Q(id_empresa__in=get_empresas_visible(self.request.user))
        ).select_related("id_moneda_origen", "id_moneda_destino", "id_usuario_registro", "id_tipo_tasa")


from rest_framework.decorators import action

from apps.core.models import Empresa


class MetodoPagoViewSet(_CatalogoTenantGuardMixin, BaseModelViewSet):
    _guard_empresa_field = "empresa"
    _guard_global_flags = ("es_generico", "es_publico")
    _guard_recurso_nombre = "métodos de pago"
    _guard_auto_empresa_en_create = True
    # SEC-A1 (auditoría 2026-06-10): se eliminó el override de get_object que
    # bypaseaba get_queryset() para la acción `reutilizar` — permitía operar
    # métodos de pago privados de otra empresa por UUID (IDOR, CWE-639).
    # Ahora `reutilizar` solo acepta fuentes visibles para el usuario
    # (genéricas, públicas o propias), vía el get_object estándar.

    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    lookup_field = "id_metodo_pago"
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        """
        Por defecto, filtra por empresa actual salvo que sea superusuario Omni ERP.
        Incluye métodos genéricos, públicos y de la(s) empresa(s) del usuario.
        """
        user = self.request.user
        if getattr(user, "es_superusuario_omni", False):
            return MetodoPago.objects.select_related("empresa").prefetch_related("monedas")
        empresas_usuario = get_empresas_visible(user)
        metodos_visibles = (
            MetodoPago.objects.filter(
                models.Q(es_generico=True) | models.Q(es_publico=True) | models.Q(empresa__in=empresas_usuario)
            )
            .select_related("empresa")
            .prefetch_related("monedas")
            .distinct()
        )
        return metodos_visibles

    @action(detail=False, methods=["get"], url_path="buscar_reutilizar")
    def buscar_reutilizar(self, request):
        """
        Devuelve métodos de pago reutilizables (genéricos o públicos) para la empresa actual.
        Marca con 'aplicado' los que ya están en la empresa actual (por nombre y tipo).

        SEC-A3 (auditoría 2026-06-10): antes el queryset incluía los métodos
        privados de TODOS los demás tenants serializados con `__all__`
        (`documento_json`, `referencia_externa`). Ahora solo expone métodos
        `es_generico`/`es_publico` y proyecta únicamente campos no sensibles
        (MetodoPagoReutilizableSerializer).
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.core.viewsets import get_empresas_visible

        from .serializers import MetodoPagoReutilizableSerializer

        id_empresa_actual = request.query_params.get("id_empresa_actual")
        if id_empresa_actual:
            # R-CODE-1: la "empresa actual" debe ser visible para el usuario;
            # si no, sería un oráculo sobre los métodos de otro tenant (vía
            # `aplicado` y la exclusión por empresa).
            try:
                empresa_visible = get_empresas_visible(request.user).filter(id_empresa=id_empresa_actual).exists()
            except (ValueError, DjangoValidationError):
                empresa_visible = False
            if not empresa_visible:
                return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        queryset = MetodoPago.objects.filter(models.Q(es_generico=True) | models.Q(es_publico=True))
        if id_empresa_actual:
            queryset = queryset.exclude(empresa=id_empresa_actual)
        nombre_metodo = request.query_params.get("nombre_metodo")
        tipo_metodo = request.query_params.get("tipo_metodo")
        if nombre_metodo:
            queryset = queryset.filter(nombre_metodo__icontains=nombre_metodo)
        if tipo_metodo:
            queryset = queryset.filter(tipo_metodo=tipo_metodo)
        page = self.paginate_queryset(queryset)
        serializer_context = self.get_serializer_context()
        serializer_context["id_empresa_actual"] = id_empresa_actual
        if id_empresa_actual:
            from .cache import obtener_metodos_pago_empresa_nombres

            metodos_por_tipo: dict[str, list[str]] = {}
            for tipo, nombre in obtener_metodos_pago_empresa_nombres(uuid.UUID(str(id_empresa_actual))):
                metodos_por_tipo.setdefault(tipo, []).append(nombre)
            serializer_context["metodos_empresa_por_tipo"] = metodos_por_tipo
        if page is not None:
            serializer = MetodoPagoReutilizableSerializer(page, many=True, context=serializer_context)
            return self.get_paginated_response(serializer.data)
        serializer = MetodoPagoReutilizableSerializer(queryset, many=True, context=serializer_context)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reutilizar")
    def reutilizar(self, request, *args, **kwargs):
        """
        Asocia el método de pago existente a la empresa indicada (sin copiar, solo crea la relación).
        Si ya existe para esa empresa, retorna error.
        """
        metodo = self.get_object()
        id_empresa = request.data.get("id_empresa")
        if not id_empresa:
            return Response({"detail": "id_empresa es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        # SEC-A2 (auditoría 2026-06-10): la empresa destino DEBE ser visible
        # para el usuario (R-CODE-1). Antes se resolvía con
        # Empresa.objects.get(...) sin scope, permitiendo crear métodos de
        # pago (copiando documento_json) en cualquier tenant.
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.core.viewsets import get_empresas_visible

        try:
            empresa = get_empresas_visible(request.user).get(id_empresa=id_empresa)
        except (Empresa.DoesNotExist, ValueError, DjangoValidationError):
            return Response({"detail": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        # Validación fuzzy robusta: rapidfuzz ratio, distancia Levenshtein, substring y normalización de acentos
        import unicodedata

        from rapidfuzz.distance import Levenshtein
        from rapidfuzz.fuzz import ratio

        def normalizar(s):
            s = s.lower().replace(" ", "")
            s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
            return s

        nombre_actual = normalizar(metodo.nombre_metodo)
        metodos_existentes = MetodoPago.objects.filter(empresa=empresa, tipo_metodo=metodo.tipo_metodo)
        for mp in metodos_existentes:
            nombre_db = normalizar(mp.nombre_metodo)
            sim = ratio(nombre_actual, nombre_db)
            dist = Levenshtein.distance(nombre_actual, nombre_db)
            if sim >= 55 or dist <= 3 or nombre_actual in nombre_db or nombre_db in nombre_actual:
                return Response(
                    {"detail": f"Ya existe un método de pago similar ('{mp.nombre_metodo}') para esta empresa."},
                    status=status.HTTP_409_CONFLICT,
                )
        # Asociar (crear nuevo registro con los mismos datos, pero empresa diferente)
        nuevo = MetodoPago.objects.create(
            empresa=empresa,
            nombre_metodo=metodo.nombre_metodo,
            tipo_metodo=metodo.tipo_metodo,
            activo=True,
            referencia_externa=metodo.referencia_externa,
            documento_json=metodo.documento_json,
            es_generico=False,
            es_publico=False,
        )
        serializer = self.get_serializer(nuevo)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="monedas_info")
    def monedas_info(self, request, pk=None):
        """
        Devuelve las monedas asociadas, sugeridas y obligatorias para el método de pago y la empresa indicada (por query param o usuario).
        """
        metodo = self.get_object()
        empresa_id = request.query_params.get("empresa")
        empresa = None
        if empresa_id:
            # SEC-B3 (R-CODE-1): el query param `empresa` se valida contra las
            # empresas visibles del usuario; un id ajeno o malformado → 404.
            from django.core.exceptions import ValidationError

            from apps.core.viewsets import get_empresas_visible

            try:
                empresa = get_empresas_visible(request.user).filter(id_empresa=empresa_id).first()
            except (ValueError, ValidationError):
                empresa = None
            if empresa is None:
                return Response(
                    {"detail": "Empresa no encontrada o sin acceso."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        if not empresa and hasattr(request.user, "empresas"):
            empresa = request.user.empresas.first() if request.user.empresas.exists() else None
        # Monedas asociadas globalmente
        asociadas = metodo.monedas.all()
        # Monedas activas para la empresa
        activas = (
            MonedaEmpresaActiva.objects.filter(empresa=empresa, activa=True).values_list("moneda_id", flat=True)
            if empresa
            else []
        )
        # Sugeridas: todas las públicas y las privadas de la empresa
        sugeridas = Moneda.objects.filter(models.Q(es_publica=True) | models.Q(empresa=empresa))
        # Obligatorias: si es efectivo, todas las fiat públicas
        obligatorias = []
        if metodo.tipo_metodo == "EFECTIVO":
            obligatorias = list(Moneda.objects.filter(tipo_moneda="fiat", es_publica=True))
        elif metodo.tipo_metodo == "CHEQUE":
            obligatorias = list(Moneda.objects.filter(tipo_moneda="fiat", es_publica=True))
        return Response(
            {
                "asociadas": [m.id_moneda for m in asociadas],
                "activas_empresa": list(activas),
                "sugeridas": [m.id_moneda for m in sugeridas],
                "obligatorias": [m.id_moneda for m in obligatorias],
            }
        )


class TransaccionFinancieraViewSet(BaseModelViewSet):
    queryset = TransaccionFinanciera.objects.all()
    serializer_class = TransaccionFinancieraSerializer
    pagination_class = None  # Deshabilitar paginación para ver todas las transacciones

    def perform_create(self, serializer):
        # FE-HIGH-12: la empresa se deriva del usuario, no del payload. Si el
        # cliente envía un id_empresa que NO está entre sus empresas visibles,
        # se ignora y se usa la primaria del usuario.
        from apps.core.viewsets import get_empresas_visible

        empresas = get_empresas_visible(self.request.user)
        id_empresa = serializer.validated_data.get("id_empresa")
        if id_empresa is not None and empresas.filter(pk=id_empresa.pk).exists():
            serializer.save()
            return
        empresa = empresas.first()
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(id_empresa=empresa)

    def get_queryset(self):
        # FE-HIGH-12: SIEMPRE acotar a empresas visibles del usuario. Un
        # id_empresa en query string no puede escapar el tenant porque se
        # aplica sobre el queryset ya filtrado.
        from apps.core.viewsets import get_empresas_visible

        empresas = get_empresas_visible(self.request.user)
        qs = TransaccionFinanciera.objects.filter(id_empresa__in=empresas).select_related(
            "id_empresa",
            "id_usuario_registro",
            "id_moneda_transaccion",
            "id_moneda_base",
            "id_moneda_pais_empresa",
            "id_metodo_pago",
        )
        id_empresa = self.request.query_params.get("id_empresa")
        if id_empresa:
            qs = qs.filter(id_empresa=id_empresa)
        return qs


class MovimientoCajaBancoViewSet(BaseModelViewSet):
    queryset = MovimientoCajaBanco.objects.all()
    serializer_class = MovimientoCajaBancoSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        from apps.core.viewsets import get_empresas_visible

        return MovimientoCajaBanco.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user)
        ).select_related("id_moneda", "id_caja", "id_caja__sucursal", "id_caja__empresa", "id_usuario_registro")


class CajaViewSet(BaseModelViewSet):
    queryset = Caja.objects.select_related("moneda", "empresa", "sucursal", "caja_fisica").prefetch_related(
        "metodos_pago"
    )
    serializer_class = CajaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtrar por empresas del usuario, salvo que sea superusuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(empresa__in=get_empresas_visible(user))
        return queryset

    @action(detail=True, methods=["post"], url_path="cierre")
    def cierre_caja(self, request, pk=None):
        """
        Realiza el cierre de la caja virtual. Recibe el saldo real contado y
        opcionalmente 'hasta' (fecha/hora límite ISO). El corte queda
        persistido como MovimientoCajaBanco tipo CIERRE (patrón PR #73).

        FIX (endpoint roto): llamaba ``caja.realizar_cierre`` pero ``Caja``
        (virtual) no definía ese método → siempre 400. Ahora el método existe
        y reutiliza el helper común ``services.realizar_cierre_caja``.
        """
        from decimal import Decimal, InvalidOperation

        from django.utils.dateparse import parse_datetime

        # R-CODE-1: get_object() aplica el filtro de tenant del ViewSet → 404
        # si la caja pertenece a otra empresa.
        caja = self.get_object()
        saldo_real = request.data.get("saldo_real")
        if saldo_real is None:
            return Response({"error": "Debe enviar el saldo_real contado."}, status=400)
        try:
            # R-CODE-4: nunca Decimal(float); pasar por str preserva el valor.
            saldo_real = Decimal(str(saldo_real))
        except (InvalidOperation, ValueError, TypeError):
            return Response({"error": "El saldo_real enviado no es un número válido."}, status=400)
        hasta = request.data.get("hasta")
        hasta_dt = parse_datetime(hasta) if hasta else None
        if hasta and hasta_dt is None:
            return Response({"error": "El parámetro 'hasta' no tiene un formato de fecha/hora válido."}, status=400)
        usuario = request.user if request.user.is_authenticated else None
        try:
            resultado = caja.realizar_cierre(saldo_real=saldo_real, usuario=usuario, hasta=hasta_dt)
        except ValueError as exc:
            # Mensajes de negocio controlados (límite anterior al último
            # cierre); no se expone ningún detalle interno.
            return domain_error_response(exc, status_code=400)
        except Exception:
            logger.exception("Error al realizar cierre de caja")
            return Response({"error": "No se pudo realizar el cierre. Intente de nuevo."}, status=400)
        return Response(resultado)

    @action(detail=False, methods=["get"], url_path="tipo-caja-choices")
    def tipo_caja_choices(self, request):
        """
        Devuelve las opciones disponibles para el campo tipo_caja.
        """
        from .models import Caja

        return Response([{"value": value, "display": display} for value, display in Caja.TIPO_CAJA_CHOICES])

    @action(detail=True, methods=["get"], url_path="movimientos-caja-banco")
    def movimientos_caja_banco(self, request, pk=None):
        """
        Devuelve los movimientos de caja asociados a esta caja.
        Permite filtrar por fecha, tipo, moneda, concepto, referencia, usuario.
        """
        # H-SEC-8: get_object() aplica el filtro de tenant del ViewSet → 404
        # si la caja es de otra empresa. No usar pk crudo.
        caja = self.get_object()
        qs = MovimientoCajaBanco.objects.filter(id_caja=caja).select_related(
            "id_moneda", "id_caja", "id_caja__sucursal", "id_caja__empresa", "id_usuario_registro"
        )
        # Filtros opcionales
        fecha_inicio = request.query_params.get("fecha_inicio")
        fecha_fin = request.query_params.get("fecha_fin")
        tipo = request.query_params.get("tipo")
        moneda = request.query_params.get("moneda")
        concepto = request.query_params.get("concepto")
        referencia = request.query_params.get("referencia")
        usuario = request.query_params.get("usuario")
        if fecha_inicio:
            qs = qs.filter(fecha_movimiento__gte=fecha_inicio)
        if fecha_fin:
            qs = qs.filter(fecha_movimiento__lte=fecha_fin)
        if tipo:
            qs = qs.filter(tipo_movimiento__icontains=tipo)
        if moneda:
            qs = qs.filter(id_moneda__codigo_iso__icontains=moneda)
        if concepto:
            qs = qs.filter(concepto__icontains=concepto)
        if referencia:
            qs = qs.filter(referencia__icontains=referencia)
        if usuario:
            qs = qs.filter(id_usuario_registro__username__icontains=usuario)
        # Ordenar por fecha y hora descendente
        qs = qs.order_by("-fecha_movimiento", "-hora_movimiento")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = MovimientoCajaBancoSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = MovimientoCajaBancoSerializer(qs, many=True)
        return Response(serializer.data)


class CuentaBancariaEmpresaViewSet(NulSafeFilterMixin, BaseModelViewSet):
    queryset = CuentaBancariaEmpresa.objects.all()
    serializer_class = CuentaBancariaEmpresaSerializer
    search_fields = ["nombre_banco", "numero_cuenta", "tipo_cuenta"]
    ordering_fields = ["nombre_banco", "numero_cuenta", "saldo_actual", "fecha_creacion", "activo"]

    @action(detail=True, methods=["get"], url_path="movimientos-cuenta-bancaria")
    def movimientos_cuenta_bancaria(self, request, pk=None):
        """
        Devuelve los movimientos de la cuenta bancaria asociados a esta cuenta.
        Permite filtrar por fecha, tipo, moneda, concepto, referencia, usuario.
        """
        # H-SEC-8: get_object() aplica el filtro de tenant del ViewSet → 404
        # si la cuenta es de otra empresa. No usar pk crudo.
        cuenta = self.get_object()
        qs = MovimientoCajaBanco.objects.filter(id_cuenta_bancaria=cuenta).select_related(
            "id_moneda", "id_caja", "id_caja__sucursal", "id_caja__empresa", "id_usuario_registro"
        )
        # Filtros opcionales
        fecha_inicio = request.query_params.get("fecha_inicio")
        fecha_fin = request.query_params.get("fecha_fin")
        tipo = request.query_params.get("tipo")
        moneda = request.query_params.get("moneda")
        concepto = request.query_params.get("concepto")
        referencia = request.query_params.get("referencia")
        usuario = request.query_params.get("usuario")
        if fecha_inicio:
            qs = qs.filter(fecha_movimiento__gte=fecha_inicio)
        if fecha_fin:
            qs = qs.filter(fecha_movimiento__lte=fecha_fin)
        if tipo:
            qs = qs.filter(tipo_movimiento__icontains=tipo)
        if moneda:
            qs = qs.filter(id_moneda__codigo_iso__icontains=moneda)
        if concepto:
            qs = qs.filter(concepto__icontains=concepto)
        if referencia:
            qs = qs.filter(referencia__icontains=referencia)
        if usuario:
            qs = qs.filter(id_usuario_registro__username__icontains=usuario)
        qs = qs.order_by("-fecha_movimiento", "-hora_movimiento")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = MovimientoCajaBancoSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = MovimientoCajaBancoSerializer(qs, many=True)
        return Response(serializer.data)

    def get_queryset(self) -> models.QuerySet[CuentaBancariaEmpresa]:
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        qs = (
            CuentaBancariaEmpresa.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
            .select_related("id_moneda")
            .prefetch_related("metodos_pago", "monedas")
        )
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa_id=uuid.UUID(validar_uuid_param(empresa_id, "empresa")))
        return qs


class MonedaEmpresaActivaViewSet(BaseModelViewSet):
    queryset = MonedaEmpresaActiva.objects.all()
    serializer_class = MonedaEmpresaActivaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        user = self.request.user
        qs = MonedaEmpresaActiva.objects.select_related("empresa", "moneda")
        # Superusuario Omni ERP puede ver todas, pero aún se permite filtrar por query params
        if not getattr(user, "es_superusuario_omni", False):
            empresas = get_empresas_visible(user)
            qs = qs.filter(empresa__in=empresas)

        # Filtros por query params
        empresa_param = self.request.query_params.get("empresa")
        if empresa_param:
            qs = qs.filter(empresa=empresa_param)
        activa_param = self.request.query_params.get("activa")
        if activa_param is not None:
            # acepta 'true'/'false' o '1'/'0'
            val = str(activa_param).strip().lower()
            if val in ("1", "true", "t", "yes", "y"):
                qs = qs.filter(activa=True)
            elif val in ("0", "false", "f", "no", "n"):
                qs = qs.filter(activa=False)
        return qs


# ViewSet para CajaUsuario
class CajaUsuarioViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = CajaUsuario.objects.all()
    serializer_class = CajaUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las cajas asignadas al usuario actual.
        """
        return CajaUsuario.objects.filter(usuario=self.request.user).select_related(
            "caja", "caja__moneda", "caja__sucursal"
        )

    @action(detail=True, methods=["post"], url_path="crear-caja-virtual")
    def crear_caja_virtual(self, request, pk=None):
        """
        Crea una caja virtual en la sesión ABIERTA de la caja física asociada
        a esta asignación usuario-caja. Útil para escenarios venezolanos donde
        un mismo puesto atiende diferentes tipos de pago.

        FIX (bugs lote 4): trataba la ``CajaUsuario`` como si fuera una sesión
        (``sesion.estado`` / ``sesion.crear_caja_virtual``), atributos que el
        modelo no tiene → AttributeError 500 en toda invocación (mismo patrón
        del lote 3). Ahora resuelve la sesión ABIERTA real de la caja física
        de la caja asignada y delega en ``SesionCajaFisica.crear_caja_virtual``
        (creación real de la ``Caja`` + métodos de pago + asignación al usuario).
        """
        from .models import SesionCajaFisica

        # R-CODE-1: get_object() está acotado por get_queryset al usuario actual.
        caja_usuario = self.get_object()
        caja_fisica = caja_usuario.caja.caja_fisica
        if caja_fisica is None:
            return Response(
                {"error": "La caja asignada no está asociada a una caja física."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sesion = SesionCajaFisica.obtener_sesion_activa(caja_fisica)
        if sesion is None:
            return Response(
                {"error": "No se pueden crear cajas virtuales en una sesión cerrada"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            caja_virtual = sesion.crear_caja_virtual(
                nombre=request.data.get("nombre"),
                monedas_ids=request.data.get("monedas", []),
                metodos_pago_ids=request.data.get("metodos_pago", []),
                usuario=request.user,
            )
        except ValueError as exc:
            # Mensajes de negocio controlados (nombre/moneda/método); el de
            # moneda/método es neutro — no filtra existencia ajena (R-CODE-1).
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "mensaje": f"Caja virtual '{caja_virtual.nombre}' creada exitosamente",
                "caja_virtual": CajaSerializer(caja_virtual).data,
            }
        )


# ViewSet para CajaVirtualUsuario
class CajaVirtualUsuarioViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = CajaVirtualUsuario.objects.all()
    serializer_class = CajaVirtualUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las cajas virtuales asignadas al usuario actual.
        """
        return CajaVirtualUsuario.objects.filter(usuario=self.request.user).select_related(
            "caja_virtual", "caja_virtual__moneda", "caja_virtual__sucursal"
        )


# ViewSet para CajaFisicaUsuario
class CajaFisicaUsuarioViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = CajaFisicaUsuario.objects.all()
    serializer_class = CajaFisicaUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las cajas físicas asignadas al usuario actual.
        """
        return CajaFisicaUsuario.objects.filter(usuario=self.request.user).select_related(
            "caja_fisica", "caja_fisica__sucursal"
        )


class PlantillaMaestroCajasVirtualesViewSet(BaseModelViewSet):
    queryset = PlantillaMaestroCajasVirtuales.objects.all()
    serializer_class = PlantillaMaestroCajasVirtualesSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("empresa", "creada_por", "moneda_base")
            .prefetch_related("metodos_pago_base")
        )
        user = self.request.user

        # Filtrar por empresas visibles del usuario
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(empresa__in=get_empresas_visible(user))

        return queryset

    @action(detail=True, methods=["post"], url_path="sincronizar")
    def sincronizar(self, request, pk=None):
        """
        Fuerza la sincronización de todas las cajas virtuales basadas en esta plantilla.
        """
        plantilla = self.get_object()
        plantilla.sincronizar_cajas_virtuales()

        return Response({"mensaje": f"Sincronización completada para plantilla {plantilla.nombre}"})


class CajaVirtualAutoViewSet(BaseModelViewSet):
    queryset = CajaVirtualAuto.objects.all()
    serializer_class = CajaVirtualAutoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("caja_fisica", "empleado", "plantilla_maestro", "moneda", "metodo_pago")
        )
        user = self.request.user

        # Filtrar por empresas visibles del usuario
        if not getattr(user, "es_superusuario_omni", False):
            empresas_visibles = get_empresas_visible(user)
            queryset = queryset.filter(
                models.Q(caja_fisica__empresa__in=empresas_visibles)
                | models.Q(plantilla_maestro__empresa__in=empresas_visibles)
            )

        return queryset


class CajaMetodoPagoOverrideViewSet(BaseModelViewSet):
    queryset = CajaMetodoPagoOverride.objects.all()
    serializer_class = CajaMetodoPagoOverrideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("sucursal", "metodo_pago", "creado_por", "caja_fisica")
        user = self.request.user

        # Filtrar por empresas visibles del usuario
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(caja_fisica__empresa__in=get_empresas_visible(user))

        return queryset


# --- ViewSets para Datafono ---


class DatafonoViewSet(BaseModelViewSet):
    queryset = Datafono.objects.all()
    serializer_class = DatafonoSerializer

    def get_queryset(self):
        from apps.core.viewsets import get_empresas_visible

        # R-CODE-1: SIEMPRE acotar al tenant del usuario; los query params solo
        # estrechan dentro de las empresas visibles (antes filtraban de forma
        # opcional → fuga cross-tenant si no se pasaba id_empresa).
        queryset = (
            Datafono.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
            .select_related("id_empresa", "id_sucursal", "id_caja_fisica", "id_cuenta_bancaria_asociada")
            .prefetch_related("metodos_pago", "monedas")
        )
        id_empresa = self.request.query_params.get("id_empresa")
        id_caja_fisica = self.request.query_params.get("id_caja_fisica")
        if id_empresa:
            queryset = queryset.filter(id_empresa=id_empresa)
        if id_caja_fisica:
            queryset = queryset.filter(id_caja_fisica=id_caja_fisica)
        return queryset

    @action(detail=True, methods=["post"], url_path="cerrar-sesion")
    def cerrar_sesion_datafono(self, request, pk=None):
        """
        Cierra la sesión activa del datafono y crea un depósito consolidado.
        """
        from .models import cerrar_sesion_datafono

        datafono = self.get_object()
        usuario = request.user

        try:
            deposito = cerrar_sesion_datafono(datafono, usuario)
            serializer = DepositoDatafonoSerializer(deposito)
            return Response(
                {
                    "success": True,
                    "message": "Sesión cerrada y depósito creado exitosamente",
                    "deposito": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except ValueError:
            logger.exception("Error al cerrar sesión datafono")
            return Response(
                {"success": False, "message": "No se pudo cerrar la sesión. Intente de nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="registrar-pago")
    def registrar_pago_tarjeta(self, request, pk=None):
        """
        Registra un pago con tarjeta en el datafono.
        """
        from .models import registrar_pago_tarjeta

        datafono = self.get_object()
        usuario = request.user

        # Validar datos requeridos
        monto = request.data.get("monto")
        referencia = request.data.get("referencia_bancaria")
        transaccion_financiera_id = request.data.get("id_transaccion_financiera_origen")

        if not all([monto, referencia, transaccion_financiera_id]):
            return Response(
                {
                    "success": False,
                    "message": "Se requieren: monto, referencia_bancaria, id_transaccion_financiera_origen",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from django.core.exceptions import ValidationError as DjangoValidationError

            from .models import TransaccionFinanciera

            try:
                transaccion_financiera = TransaccionFinanciera.objects.get(
                    id_transaccion=transaccion_financiera_id,
                    id_empresa=datafono.id_empresa,
                )
            except (TransaccionFinanciera.DoesNotExist, DjangoValidationError, ValueError, TypeError):
                return Response(
                    {"success": False, "message": "Transacción financiera no encontrada"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            transaccion = registrar_pago_tarjeta(
                datafono=datafono,
                monto=monto,
                referencia=referencia,
                transaccion_financiera=transaccion_financiera,
                usuario=usuario,
            )

            serializer = TransaccionDatafonoSerializer(transaccion)
            return Response(
                {"success": True, "message": "Pago registrado exitosamente", "transaccion": serializer.data},
                status=status.HTTP_201_CREATED,
            )

        except ValueError:
            logger.exception("Error al registrar pago tarjeta")
            return Response(
                {"success": False, "message": "No se pudo registrar el pago. Verifique los datos."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class TransaccionDatafonoViewSet(BaseModelViewSet):
    queryset = TransaccionDatafono.objects.all()
    serializer_class = TransaccionDatafonoSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related("id_datafono", "id_usuario_registro", "sesion_datafono")
        # Filtrar por empresas visibles del usuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(id_datafono__id_empresa__in=get_empresas_visible(user))
        return queryset


class SesionDatafonoViewSet(BaseModelViewSet):
    queryset = SesionDatafono.objects.all()
    serializer_class = SesionDatafonoSerializer

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("datafono", "usuario_apertura")
            .annotate(_cantidad_transacciones=models.Count("transacciones_datafono"))
        )
        # Filtrar por empresas visibles del usuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(datafono__id_empresa__in=get_empresas_visible(user))
        return queryset


class DepositoDatafonoViewSet(BaseModelViewSet):
    queryset = DepositoDatafono.objects.all()
    serializer_class = DepositoDatafonoSerializer

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("datafono", "sesion_datafono", "usuario_envio", "usuario_conciliacion", "movimiento_banco")
        )
        # Filtrar por empresas visibles del usuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(datafono__id_empresa__in=get_empresas_visible(user))
        return queryset

    @action(detail=True, methods=["post"], url_path="conciliar")
    def conciliar_deposito(self, request, pk=None):
        """
        Conciliar un depósito con un movimiento bancario recibido.
        """
        from .models import conciliar_deposito_datafono

        deposito = self.get_object()
        usuario = request.user

        movimiento_banco_id = request.data.get("id_movimiento_banco")
        if not movimiento_banco_id:
            return Response(
                {"success": False, "message": "Se requiere id_movimiento_banco"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from django.core.exceptions import ValidationError as DjangoValidationError

            from .models import MovimientoCajaBanco

            try:
                movimiento_banco = MovimientoCajaBanco.objects.get(
                    id_movimiento=movimiento_banco_id,
                    id_empresa=deposito.datafono.id_empresa,
                )
            except (MovimientoCajaBanco.DoesNotExist, DjangoValidationError, ValueError, TypeError):
                return Response(
                    {"success": False, "message": "Movimiento bancario no encontrado"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            deposito = conciliar_deposito_datafono(deposito, movimiento_banco, usuario)

            serializer = DepositoDatafonoSerializer(deposito)
            return Response(
                {"success": True, "message": "Depósito conciliado exitosamente", "deposito": serializer.data},
                status=status.HTTP_200_OK,
            )

        except ValueError:
            logger.exception("Error al conciliar depósito")
            return Response(
                {"success": False, "message": "No se pudo conciliar el depósito. Verifique los datos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"], url_path="pendientes")
    def depositos_pendientes(self, request):
        """
        Obtener depósitos pendientes de conciliación.
        """
        from .models import obtener_depositos_pendientes

        empresas = get_empresas_visible(request.user)
        datafono_id = request.query_params.get("datafono_id")
        datafono = None
        if datafono_id:
            from django.core.exceptions import ValidationError as DjangoValidationError

            try:
                datafono = Datafono.objects.get(id_datafono=datafono_id, id_empresa__in=empresas)
            except (Datafono.DoesNotExist, DjangoValidationError, ValueError, TypeError):
                return Response(
                    {"success": False, "message": "Datafono no encontrado"}, status=status.HTTP_404_NOT_FOUND
                )

        depositos = (
            obtener_depositos_pendientes(datafono)
            .filter(datafono__id_empresa__in=empresas)
            .select_related("datafono", "sesion_datafono", "usuario_envio", "usuario_conciliacion", "movimiento_banco")
        )
        serializer = self.get_serializer(depositos, many=True)

        return Response({"success": True, "depositos": serializer.data}, status=status.HTTP_200_OK)


class CajaFisicaViewSet(BaseModelViewSet):
    queryset = CajaFisica.objects.all()
    serializer_class = CajaFisicaSerializer

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("empresa", "sucursal")
            .prefetch_related(
                models.Prefetch(
                    "cajas_virtuales",
                    queryset=Caja.objects.select_related(
                        "empresa", "sucursal", "moneda", "caja_fisica"
                    ).prefetch_related("metodos_pago"),
                ),
                models.Prefetch(
                    "datafonos",
                    queryset=Datafono.objects.select_related(
                        "id_empresa", "id_sucursal", "id_caja_fisica", "id_cuenta_bancaria_asociada"
                    ).prefetch_related("metodos_pago", "monedas"),
                ),
                models.Prefetch(
                    "sesiones",
                    queryset=SesionCajaFisica.objects.filter(estado="ABIERTA").select_related("usuario"),
                    to_attr="_prefetched_sesiones_abiertas",
                ),
            )
        )
        # Filtrar por empresas del usuario, salvo que sea superusuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            queryset = queryset.filter(empresa__in=get_empresas_visible(user))
        return queryset

    # BUG-C2: aquí vivía un perform_create que trataba la CajaFisica creada
    # como si fuera un Pago (creaba TransaccionFinanciera/MovimientoCajaBanco)
    # → todo POST de caja física reventaba con AttributeError 500. Esa lógica
    # ahora vive en apps.finanzas.services.registrar_efectos_pago y la invoca
    # PagoViewSet.perform_create.

    @action(detail=True, methods=["post"], url_path="cierre")
    def cierre(self, request, pk=None):
        """
        Realiza el cierre de la caja física (hallazgo P0-8): el frontend llama
        POST /finanzas/cajas-fisicas/{id}/cierre, ruta que no existía. Recibe
        saldo_real (contado) y opcionalmente 'hasta' (fecha/hora límite ISO).
        El corte queda persistido como MovimientoCajaBanco tipo CIERRE.
        """
        from decimal import Decimal, InvalidOperation

        from django.utils.dateparse import parse_datetime

        # R-CODE-1: get_object() aplica el filtro de tenant del ViewSet → 404
        # si la caja física pertenece a otra empresa.
        caja = self.get_object()
        saldo_real = request.data.get("saldo_real")
        if saldo_real is None:
            return Response({"error": "Debe enviar el saldo_real contado."}, status=400)
        try:
            # R-CODE-4: nunca Decimal(float); pasar por str preserva el valor.
            saldo_real = Decimal(str(saldo_real))
        except (InvalidOperation, ValueError, TypeError):
            return Response({"error": "El saldo_real enviado no es un número válido."}, status=400)
        hasta = request.data.get("hasta")
        hasta_dt = parse_datetime(hasta) if hasta else None
        if hasta and hasta_dt is None:
            return Response({"error": "El parámetro 'hasta' no tiene un formato de fecha/hora válido."}, status=400)
        usuario = request.user if request.user.is_authenticated else None
        try:
            resultado = caja.realizar_cierre(saldo_real=saldo_real, usuario=usuario, hasta=hasta_dt)
        except ValueError as exc:
            # Mensajes de negocio controlados (límite anterior al último
            # cierre); no se expone ningún detalle interno.
            return domain_error_response(exc, status_code=400)
        except Exception:
            logger.exception("Error al realizar cierre de caja física")
            return Response({"error": "No se pudo realizar el cierre. Intente de nuevo."}, status=400)
        return Response(resultado)

    @action(detail=True, methods=["post"], url_path="abrir-sesion")
    def abrir_sesion(self, request, pk=None):
        """
        Abre una sesión de trabajo sobre esta caja física (FIX endpoint roto:
        el frontend llama POST /finanzas/cajas-fisicas/{id}/abrir-sesion/ y la
        ruta no existía). Si había una sesión abierta, se cierra
        automáticamente (comportamiento de SesionCajaFisica.abrir_sesion).
        """
        from .models import SesionCajaFisica

        # R-CODE-1: get_object() aplica el filtro de tenant del ViewSet → 404
        # si la caja física pertenece a otra empresa.
        caja = self.get_object()
        try:
            sesion = SesionCajaFisica.abrir_sesion(
                caja_fisica=caja,
                usuario=request.user,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:1000] or None,
            )
        except ValueError as exc:
            # Carrera de doble apertura (bugs lote 4): 400 de negocio, no 500.
            return domain_error_response(exc, status_code=400)
        return Response(
            {
                "mensaje": f"Sesión abierta para la caja {caja.nombre}.",
                "sesion": {
                    "id_sesion": str(sesion.id_sesion),
                    "estado": sesion.estado,
                    "fecha_apertura": sesion.fecha_apertura,
                    "usuario": sesion.usuario.username,
                },
            }
        )

    @action(detail=True, methods=["post"], url_path="cerrar-sesion")
    def cerrar_sesion(self, request, pk=None):
        """
        Cierra la sesión ABIERTA de esta caja física (FIX endpoint roto: el
        frontend llama POST /finanzas/cajas-fisicas/{id}/cerrar-sesion/ y la
        ruta no existía). Acepta opcionalmente ``notas_cierre``,
        ``saldos_reales`` ({id_caja: saldo real contado} — la propia caja
        física y/o sus cajas virtuales) y ``hasta``; los cierres por caja y el
        cambio de estado de la sesión son atómicos
        (SesionCajaFisica.cerrar_sesion).
        """
        from django.utils.dateparse import parse_datetime

        from .models import SesionCajaFisica

        # R-CODE-1: tenant via get_object() → 404 si la caja es ajena.
        caja = self.get_object()
        sesion = SesionCajaFisica.obtener_sesion_activa(caja)
        if sesion is None:
            return Response({"error": "No hay una sesión abierta para esta caja física."}, status=400)
        saldos_reales = request.data.get("saldos_reales") or {}
        if not isinstance(saldos_reales, dict):
            return Response({"error": "saldos_reales debe ser un objeto {id_caja: saldo_real}."}, status=400)
        hasta = request.data.get("hasta")
        hasta_dt = parse_datetime(hasta) if hasta else None
        if hasta and hasta_dt is None:
            return Response({"error": "El parámetro 'hasta' no tiene un formato de fecha/hora válido."}, status=400)
        try:
            cierres = sesion.cerrar_sesion(
                notas_cierre=request.data.get("notas_cierre"),
                saldos_reales=saldos_reales,
                usuario=request.user,
                hasta=hasta_dt,
            )
        except ValueError as exc:
            # Mensajes de negocio controlados; sin detalles internos.
            return domain_error_response(exc, status_code=400)
        except Exception:
            logger.exception("Error al cerrar sesión de caja física")
            return Response({"error": "No se pudo cerrar la sesión. Intente de nuevo."}, status=400)
        sesion.refresh_from_db()
        return Response(
            {
                "mensaje": f"Sesión cerrada para la caja {caja.nombre}.",
                "sesion": {
                    "id_sesion": str(sesion.id_sesion),
                    "estado": sesion.estado,
                    "fecha_cierre": sesion.fecha_cierre,
                    "duracion_minutos": sesion.duracion,
                },
                "cierres": cierres,
            }
        )

    @action(detail=False, methods=["get"])
    def tipos_documento(self, request):
        """Retorna los tipos de documento disponibles"""
        from .models import Pago

        return Response([{"value": choice[0], "label": choice[1]} for choice in Pago.TIPO_DOCUMENTO_CHOICES])

    @action(detail=False, methods=["get"])
    def tipos_operacion(self, request):
        """Retorna los tipos de operación disponibles"""
        from .models import Pago

        return Response([{"value": choice[0], "label": choice[1]} for choice in Pago.TIPO_OPERACION_CHOICES])

    @action(detail=False, methods=["get"], url_path="tipo-caja-choices")
    def tipo_caja_choices(self, request):
        """
        Devuelve las opciones disponibles para el campo tipo_caja.
        """
        from .models import CajaFisica

        return Response([{"value": value, "display": display} for value, display in CajaFisica.TIPO_CAJA_CHOICES])


class PagoViewSet(IdempotentCreateMixin, BaseModelViewSet):
    queryset = Pago.objects.all()
    serializer_class = PagoSerializer
    # P1-2: POST /pagos/ idempotente por cabecera Idempotency-Key (opt-in).
    idempotency_scope = "finanzas:pago"

    # P1-1: techo estricto para escritura de pagos (scope 'escritura');
    # los GET siguen bajo los throttles globales anon/user.
    throttle_classes = [*BaseModelViewSet.throttle_classes, EscrituraRateThrottle]
    search_fields = [
        "referencia",
        "observaciones",
        "tipo_documento",
        "id_contacto__nombre",
        "id_contacto__rif",
    ]
    ordering_fields = [
        "fecha_pago",
        "fecha_creacion",
        "monto",
        "tipo_operacion",
        "tipo_documento",
    ]

    def filter_queryset(self, queryset):
        search_param = self.request.query_params.get("search")
        if search_param and "\x00" in search_param:
            raise ValidationError({"search": "Parámetro de búsqueda inválido."})
        return super().filter_queryset(queryset)

    def perform_create(self, serializer):
        # BUG-C2: los side-effects financieros (TransaccionFinanciera +
        # MovimientoCajaBanco + saldos) van en la MISMA transacción que el
        # Pago (R-CODE-11); el service aplica select_for_update sobre la
        # caja/cuenta afectada.
        from django.db import transaction

        from .services import TasaCambioError, registrar_efectos_pago

        with transaction.atomic():
            try:
                pago = serializer.save()
            except ValueError as exc:
                raise serializers.ValidationError({"detail": str(exc)}) from exc
            try:
                registrar_efectos_pago(pago)
            except TasaCambioError as exc:
                # Pago en divisa sin tasa configurada hacia la moneda base: se
                # rechaza con 400 claro (antes propagaba como 500). Nunca se
                # asume 1:1 entre monedas distintas.
                raise serializers.ValidationError({"id_moneda": str(exc)}) from exc

        if pago.tipo_operacion == "INGRESO":
            try:
                from apps.notificaciones.services import emitir_notificacion

                emitir_notificacion(
                    "PAGO_RECIBIDO",
                    pago.id_empresa,
                    self.request.user,
                    {
                        "monto": str(pago.monto),
                        "moneda": str(pago.id_moneda),
                        "numero_factura": str(pago.id_documento or pago.id_pago),
                    },
                )
            except Exception:  # noqa: BLE001
                pass  # notificación best-effort

    def perform_update(self, serializer):
        try:
            serializer.save()
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def get_queryset(self) -> models.QuerySet[Pago]:
        # R-CODE-1: usar get_empresas_visible para incluir subsidiarias y
        # garantizar aislamiento simétrico con los demás módulos.
        qs: models.QuerySet[Pago] = Pago.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user)
        ).select_related(
            "id_empresa",
            "id_contacto",
            "id_metodo_pago",
            "id_moneda",
            "id_caja_fisica",
            "id_caja_virtual",
            "id_cuenta_bancaria",
            "id_datafono",
            "banco_destino",
            "id_usuario_registro",
            "id_transaccion_financiera",
            "id_pedido__id_cliente",
            "id_nota_venta",
            "id_factura",
            "id_cxp__id_proveedor",
            "id_gasto",
            "id_reembolso_gasto",
            "id_nomina",
            "id_contribucion",
        )
        tipo_op_raw = self.request.query_params.get("tipo_operacion")
        if tipo_op_raw:
            tipo_op = str(tipo_op_raw).replace("\x00", "").strip().upper()
            if tipo_op:
                valid_ops = {c[0] for c in Pago.TIPO_OPERACION_CHOICES}
                if tipo_op not in valid_ops:
                    raise ValidationError({"tipo_operacion": f"Tipo de operación inválido: {tipo_op!r}."})
                qs = qs.filter(tipo_operacion=tipo_op)

        empresa_raw = self.request.query_params.get("id_empresa") or self.request.query_params.get("empresa")
        if empresa_raw:
            qs = qs.filter(id_empresa_id=uuid.UUID(validar_uuid_param(empresa_raw, "id_empresa")))

        return qs.order_by("-fecha_pago")

    @action(detail=False, methods=["get"])
    def tipos_documento(self, request):
        """Retorna los tipos de documento disponibles"""
        from .models import Pago

        return Response([{"value": choice[0], "label": choice[1]} for choice in Pago.TIPO_DOCUMENTO_CHOICES])

    @action(detail=False, methods=["get"])
    def tipos_operacion(self, request):
        """Retorna los tipos de operación disponibles"""
        from .models import Pago

        return Response([{"value": choice[0], "label": choice[1]} for choice in Pago.TIPO_OPERACION_CHOICES])

    @swagger_auto_schema(
        request_body=ConciliarDocumentosInputSerializer,
        responses={200: ConciliarDocumentosResponseSerializer},
    )
    @idempotent("finanzas:pago-conciliar")
    @action(detail=True, methods=["post"], url_path="conciliar-documentos")
    def conciliar_documentos(self, request, pk=None):
        """Aplica un ``Pago`` a 1..N documentos abiertos en una transacción atómica."""
        from .services_conciliacion_pagos import (
            ConciliacionPagoError,
            aplicar_pago_a_documentos,
            saldo_disponible_pago,
        )
        from .views_conciliacion_pagos import _responder_error_conciliacion

        pago = self.get_object()
        input_ser = ConciliarDocumentosInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        datos = input_ser.validated_data

        try:
            creadas = aplicar_pago_a_documentos(
                pago,
                datos["asignaciones"],
                usuario=request.user,
                generar_asiento=bool(datos.get("generar_asiento", True)),
                descripcion=str(datos.get("descripcion") or ""),
            )
        except ConciliacionPagoError as exc:
            return _responder_error_conciliacion(exc)

        return Response(
            {
                "pago_id": str(pago.pk),
                "saldo_disponible": str(saldo_disponible_pago(pago)),
                "asignaciones": AsignacionPagoSerializer(creadas, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "tipo_documento",
                openapi.IN_QUERY,
                description="Opcional: restringe sugerencia FIFO a un tipo de documento.",
                type=openapi.TYPE_STRING,
                enum=["CUENTA_POR_COBRAR", "FACTURA_VENTA", "CUENTA_POR_PAGAR", "FACTURA_COMPRA"],
            ),
        ],
        responses={200: SugerirDistribucionResponseSerializer},
    )
    @action(detail=True, methods=["get"], url_path="sugerir-distribucion")
    def sugerir_distribucion(self, request, pk=None):
        """Propone distribución FIFO determinística del saldo disponible del pago."""
        from .services_conciliacion_pagos import (
            TIPOS_DOCUMENTO_VALIDOS,
            ConciliacionPagoError,
            sugerir_distribucion_fifo,
        )
        from .views_conciliacion_pagos import _responder_error_conciliacion

        pago = self.get_object()
        tipo_doc_raw = request.query_params.get("tipo_documento")
        tipo_doc: str | None = None
        if tipo_doc_raw is not None:
            tipo_limpio = str(tipo_doc_raw).replace("\x00", "").strip()
            if tipo_limpio:
                if tipo_limpio not in TIPOS_DOCUMENTO_VALIDOS:
                    raise ValidationError({"tipo_documento": f"Tipo de documento inválido: {tipo_limpio!r}."})
                tipo_doc = tipo_limpio

        try:
            propuesta = sugerir_distribucion_fifo(pago, tipo_documento=tipo_doc)
        except ConciliacionPagoError as exc:
            return _responder_error_conciliacion(exc)

        return Response(SugerirDistribucionResponseSerializer(propuesta).data, status=status.HTTP_200_OK)


def _serializar_tasa_meta_json(meta: dict | None) -> dict | None:
    if meta is None:
        return None
    return {
        "valor_tasa": str(meta["valor_tasa"]),
        "tipo_tasa": meta["tipo_tasa"],
        "fecha_tasa": meta["fecha_tasa"].isoformat() if meta["fecha_tasa"] else None,
        "es_inversa": bool(meta["es_inversa"]),
        "es_oficial_fiscal": bool(meta["es_oficial_fiscal"]),
    }


class EquivalenciasTrimonetariasView(viewsets.views.APIView):
    """Calcula equivalencias simultáneas Base + País/Fiscal (BCV) + Referencia."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(request_body=EquivalenciasTrimonetariasInputSerializer)
    def post(self, request):
        from apps.core.viewsets import get_empresa_primaria

        from .services import TasaCambioError
        from .services_trimonetario import calcular_equivalencias_trimonetarias

        serializer = EquivalenciasTrimonetariasInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        empresa = get_empresa_primaria(request.user)
        if empresa is None:
            return Response({"error": "El usuario no tiene una empresa visible asignada."}, status=400)

        moneda_raw = str(datos["moneda_origen"]).replace("\x00", "").strip()
        moneda_arg: Moneda | str = moneda_raw
        try:
            moneda_uuid = uuid.UUID(moneda_raw)
        except (ValueError, TypeError):
            moneda_uuid = None

        if moneda_uuid is not None:
            moneda_obj = (
                Moneda.objects.filter(id_moneda=moneda_uuid)
                .filter(
                    models.Q(es_generica=True)
                    | models.Q(es_publica=True)
                    | models.Q(empresa__isnull=True)
                    | models.Q(empresa__in=get_empresas_visible(request.user))
                )
                .first()
            )
            if moneda_obj is None:
                return Response({"error": "Moneda de origen no encontrada."}, status=404)
            moneda_arg = moneda_obj

        try:
            resultado = calcular_equivalencias_trimonetarias(
                datos["monto"],
                moneda_arg,
                empresa=empresa,
                fecha=datos.get("fecha"),
                codigo_tipo_tasa_base=datos.get("codigo_tipo_tasa_base") or None,
                codigo_tipo_tasa_referencia=datos.get("codigo_tipo_tasa_referencia") or None,
            )
        except (TasaCambioError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "fecha": resultado["fecha"].isoformat(),
                "moneda_origen_id": resultado["moneda_origen_id"],
                "moneda_origen_iso": resultado["moneda_origen_iso"],
                "moneda_origen_simbolo": resultado["moneda_origen_simbolo"],
                "monto_origen": str(resultado["monto_origen"]),
                "moneda_base_id": resultado["moneda_base_id"],
                "moneda_base_iso": resultado["moneda_base_iso"],
                "moneda_base_simbolo": resultado["moneda_base_simbolo"],
                "monto_base": str(resultado["monto_base"]) if resultado["monto_base"] is not None else None,
                "tasa_base": _serializar_tasa_meta_json(resultado["tasa_base"]),
                "moneda_pais_id": resultado["moneda_pais_id"],
                "moneda_pais_iso": resultado["moneda_pais_iso"],
                "moneda_pais_simbolo": resultado["moneda_pais_simbolo"],
                "monto_pais_fiscal": (
                    str(resultado["monto_pais_fiscal"]) if resultado["monto_pais_fiscal"] is not None else None
                ),
                "tasa_pais_fiscal": _serializar_tasa_meta_json(resultado["tasa_pais_fiscal"]),
                "moneda_referencia_activa": resultado["moneda_referencia_activa"],
                "moneda_referencia_id": resultado["moneda_referencia_id"],
                "moneda_referencia_iso": resultado["moneda_referencia_iso"],
                "moneda_referencia_simbolo": resultado["moneda_referencia_simbolo"],
                "monto_referencia": (
                    str(resultado["monto_referencia"]) if resultado["monto_referencia"] is not None else None
                ),
                "tasa_referencia": _serializar_tasa_meta_json(resultado["tasa_referencia"]),
            },
            status=status.HTTP_200_OK,
        )

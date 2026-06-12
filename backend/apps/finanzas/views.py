import logging
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.throttling import EscrituraRateThrottle

from django.db import models
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.core.idempotency import IdempotentCreateMixin
from apps.core.viewsets import BaseModelViewSet
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
        return SesionCajaFisica.objects.filter(empresa__in=get_empresas_visible(self.request.user))

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
            caja_fisica = CajaFisica.objects.filter(
                empresa__in=get_empresas_visible(self.request.user)
            ).get(id_caja_fisica=caja_fisica_id, activa=True)
        except (CajaFisica.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            # R-CODE-1: mismo mensaje para inexistente, inactiva, malformada o
            # ajena — no se filtra existencia de cajas de otros tenants.
            raise serializers.ValidationError({"caja_fisica_principal": "Caja física no encontrada o no válida"})

        instance = SesionCajaFisica.abrir_sesion(
            caja_fisica=caja_fisica,
            usuario=self.request.user,
            ip_address=self.request.META.get("REMOTE_ADDR"),
            user_agent=(self.request.META.get("HTTP_USER_AGENT") or "")[:1000] or None,
        )
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
            return Response({"error": str(exc)}, status=400)
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
        if not (caja_origen_id and caja_destino_id and monto):
            return Response({"error": "Debe indicar caja_origen, caja_destino y monto."}, status=400)
        cajas_de_sesion = sesion.caja_fisica.cajas_virtuales
        try:
            caja_origen = cajas_de_sesion.get(id_caja=caja_origen_id)
            caja_destino = cajas_de_sesion.get(id_caja=caja_destino_id)
        except (Caja.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            # R-CODE-1: mismo mensaje para caja inexistente, malformada o de
            # otra sesión/tenant — no se filtra existencia de cajas ajenas.
            return Response({"error": "Caja origen o destino no pertenece a la sesión."}, status=400)
        try:
            mov_salida, mov_entrada = transferencia_entre_cajas(
                caja_origen, caja_destino, monto, usuario=usuario
            )
        except ValueError as exc:
            # Mensajes de negocio controlados (monto, saldo, moneda); no se
            # expone ningún detalle interno.
            return Response({"error": str(exc)}, status=400)
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
        )
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
    TransaccionFinanciera,
)
from .serializers import (
    CuentaBancariaEmpresaSerializer,
    MetodoPagoSerializer,
    MonedaEmpresaActivaSerializer,
    MonedaSerializer,
    MovimientoCajaBancoSerializer,
    TasaCambioSerializer,
    TransaccionFinancieraSerializer,
)


class MonedaViewSet(BaseModelViewSet):
    @action(detail=False, methods=["get"], url_path="activas")
    def activas(self, request):
        user = request.user
        if getattr(user, "es_superusuario_omni", False):
            queryset = Moneda.objects.all()
        else:
            empresas_usuario = user.empresas.all()
            monedas_visibles = Moneda.objects.filter(
                models.Q(es_generica=True) | models.Q(es_publica=True) | models.Q(empresa__in=empresas_usuario)
            ).distinct()
            if not empresas_usuario.exists():
                queryset = monedas_visibles
            else:
                empresa = empresas_usuario.first()
                activas_ids = set(
                    MonedaEmpresaActiva.objects.filter(empresa=empresa, activa=True).values_list(
                        "moneda_id", flat=True
                    )
                )
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
        empresas_usuario = user.empresas.all()
        # Monedas visibles (genéricas, públicas, propias)
        monedas_visibles = Moneda.objects.filter(
            models.Q(es_generica=True) | models.Q(es_publica=True) | models.Q(empresa__in=empresas_usuario)
        ).distinct()
        return monedas_visibles


class TasaCambioViewSet(BaseModelViewSet):
    queryset = TasaCambio.objects.all()
    serializer_class = TasaCambioSerializer

    def get_queryset(self):
        # R-CODE-1: tasas globales (BCV) son visibles para todos (id_empresa nulo),
        # las específicas se filtran por empresa visible del usuario.
        from django.db.models import Q
        from apps.core.viewsets import get_empresas_visible
        return TasaCambio.objects.filter(
            Q(id_empresa__isnull=True) | Q(id_empresa__in=get_empresas_visible(self.request.user))
        )


from rest_framework.decorators import action

from apps.core.models import Empresa


class MetodoPagoViewSet(BaseModelViewSet):
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
            return MetodoPago.objects.all()
        empresas_usuario = user.empresas.all()
        metodos_visibles = MetodoPago.objects.filter(
            models.Q(es_generico=True) | models.Q(es_publico=True) | models.Q(empresa__in=empresas_usuario)
        ).distinct()
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
                empresa_visible = (
                    get_empresas_visible(request.user).filter(id_empresa=id_empresa_actual).exists()
                )
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
                empresa = get_empresas_visible(request.user).filter(
                    id_empresa=empresa_id
                ).first()
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
        qs = TransaccionFinanciera.objects.filter(id_empresa__in=empresas)
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
        return MovimientoCajaBanco.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))


class CajaViewSet(BaseModelViewSet):
    queryset = Caja.objects.select_related("moneda", "empresa", "sucursal", "caja_fisica")
    serializer_class = CajaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtrar por empresas del usuario, salvo que sea superusuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            empresas_usuario = getattr(user, "empresas", None)
            if empresas_usuario and hasattr(empresas_usuario, "all"):
                queryset = queryset.filter(empresa__in=empresas_usuario.all())
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
            return Response({"error": str(exc)}, status=400)
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
        qs = MovimientoCajaBanco.objects.filter(id_caja=caja)
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

    queryset = Caja.objects.all()
    serializer_class = CajaSerializer


class CuentaBancariaEmpresaViewSet(BaseModelViewSet):
    from rest_framework.response import Response

    from .models import MovimientoCajaBanco
    from .serializers import MovimientoCajaBancoSerializer

    @action(detail=True, methods=["get"], url_path="movimientos-cuenta-bancaria")
    def movimientos_cuenta_bancaria(self, request, pk=None):
        """
        Devuelve los movimientos de la cuenta bancaria asociados a esta cuenta.
        Permite filtrar por fecha, tipo, moneda, concepto, referencia, usuario.
        """
        # H-SEC-8: get_object() aplica el filtro de tenant del ViewSet → 404
        # si la cuenta es de otra empresa. No usar pk crudo.
        cuenta = self.get_object()
        qs = MovimientoCajaBanco.objects.filter(id_cuenta_bancaria=cuenta)
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

    queryset = CuentaBancariaEmpresa.objects.all()
    serializer_class = CuentaBancariaEmpresaSerializer

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        from apps.core.viewsets import get_empresas_visible
        return CuentaBancariaEmpresa.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))


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
        qs = MonedaEmpresaActiva.objects.all()
        # Superusuario Omni ERP puede ver todas, pero aún se permite filtrar por query params
        if not getattr(user, "es_superusuario_omni", False):
            empresas = user.empresas.all()
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
        return CajaUsuario.objects.filter(usuario=self.request.user).select_related("caja")

    @action(detail=True, methods=["post"], url_path="crear-caja-virtual")
    def crear_caja_virtual(self, request, pk=None):
        """
        Crea una caja virtual dentro de la sesión activa.
        Útil para escenarios venezolanos donde un mismo puesto atiende diferentes tipos de pago.
        """
        sesion = self.get_object()

        # Validar que la sesión esté abierta
        if sesion.estado != "ABIERTA":
            return Response(
                {"error": "No se pueden crear cajas virtuales en una sesión cerrada"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nombre = request.data.get("nombre")
        monedas_ids = request.data.get("monedas", [])
        metodos_pago_ids = request.data.get("metodos_pago", [])

        if not nombre:
            return Response(
                {"error": "Debe especificar un nombre para la caja virtual"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            caja_virtual = sesion.crear_caja_virtual(
                nombre=nombre, monedas_ids=monedas_ids, metodos_pago_ids=metodos_pago_ids, usuario=request.user
            )
            return Response({"mensaje": f"Caja virtual '{nombre}' creada exitosamente", "caja_virtual": caja_virtual})
        except ValueError:
            logger.exception("Error al crear caja virtual")
            return Response({"error": "No se pudo crear la caja virtual. Verifique los datos."}, status=status.HTTP_400_BAD_REQUEST)


# ViewSet para CajaVirtualUsuario
class CajaVirtualUsuarioViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = CajaVirtualUsuario.objects.all()
    serializer_class = CajaVirtualUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las cajas virtuales asignadas al usuario actual.
        """
        return CajaVirtualUsuario.objects.filter(usuario=self.request.user).select_related("caja_virtual")


# ViewSet para CajaFisicaUsuario
class CajaFisicaUsuarioViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = CajaFisicaUsuario.objects.all()
    serializer_class = CajaFisicaUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las cajas físicas asignadas al usuario actual.
        """
        return CajaFisicaUsuario.objects.filter(usuario=self.request.user).select_related("caja_fisica")




class PlantillaMaestroCajasVirtualesViewSet(BaseModelViewSet):
    queryset = PlantillaMaestroCajasVirtuales.objects.all()
    serializer_class = PlantillaMaestroCajasVirtualesSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Filtrar por empresas del usuario
        empresas_usuario = getattr(user, "empresas", None)
        if empresas_usuario and hasattr(empresas_usuario, "all"):
            queryset = queryset.filter(empresa__in=empresas_usuario.all())

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
        queryset = super().get_queryset()
        user = self.request.user

        # Filtrar por empresas del usuario
        empresas_usuario = getattr(user, "empresas", None)
        if empresas_usuario and hasattr(empresas_usuario, "all"):
            queryset = queryset.filter(
                models.Q(caja_fisica__empresa__in=empresas_usuario.all())
                | models.Q(plantilla_maestro__empresa__in=empresas_usuario.all())
            )

        return queryset


class CajaMetodoPagoOverrideViewSet(BaseModelViewSet):
    queryset = CajaMetodoPagoOverride.objects.all()
    serializer_class = CajaMetodoPagoOverrideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Filtrar por empresas del usuario
        empresas_usuario = getattr(user, "empresas", None)
        if empresas_usuario and hasattr(empresas_usuario, "all"):
            queryset = queryset.filter(caja_fisica__empresa__in=empresas_usuario.all())

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
        queryset = Datafono.objects.filter(id_empresa__in=get_empresas_visible(self.request.user))
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
            return Response({"success": False, "message": "No se pudo cerrar la sesión. Intente de nuevo."}, status=status.HTTP_400_BAD_REQUEST)

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
            from .models import TransaccionFinanciera

            transaccion_financiera = TransaccionFinanciera.objects.get(id_transaccion=transaccion_financiera_id)

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

        except TransaccionFinanciera.DoesNotExist:
            return Response(
                {"success": False, "message": "Transacción financiera no encontrada"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            logger.exception("Error al registrar pago tarjeta")
            return Response({"success": False, "message": "No se pudo registrar el pago. Verifique los datos."}, status=status.HTTP_400_BAD_REQUEST)


class TransaccionDatafonoViewSet(BaseModelViewSet):
    queryset = TransaccionDatafono.objects.all()
    serializer_class = TransaccionDatafonoSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtrar por empresas del usuario
        user = self.request.user
        empresas_usuario = getattr(user, "empresas", None)
        if empresas_usuario and hasattr(empresas_usuario, "all"):
            queryset = queryset.filter(id_datafono__id_empresa__in=empresas_usuario.all())
        return queryset


class SesionDatafonoViewSet(BaseModelViewSet):
    queryset = SesionDatafono.objects.all()
    serializer_class = SesionDatafonoSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtrar por empresas del usuario
        user = self.request.user
        empresas_usuario = getattr(user, "empresas", None)
        if empresas_usuario and hasattr(empresas_usuario, "all"):
            queryset = queryset.filter(datafono__id_empresa__in=empresas_usuario.all())
        return queryset


class DepositoDatafonoViewSet(BaseModelViewSet):
    queryset = DepositoDatafono.objects.all()
    serializer_class = DepositoDatafonoSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtrar por empresas del usuario
        user = self.request.user
        empresas_usuario = getattr(user, "empresas", None)
        if empresas_usuario and hasattr(empresas_usuario, "all"):
            queryset = queryset.filter(datafono__id_empresa__in=empresas_usuario.all())
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
            from .models import MovimientoCajaBanco

            movimiento_banco = MovimientoCajaBanco.objects.get(id_movimiento=movimiento_banco_id)

            deposito = conciliar_deposito_datafono(deposito, movimiento_banco, usuario)

            serializer = DepositoDatafonoSerializer(deposito)
            return Response(
                {"success": True, "message": "Depósito conciliado exitosamente", "deposito": serializer.data},
                status=status.HTTP_200_OK,
            )

        except MovimientoCajaBanco.DoesNotExist:
            return Response(
                {"success": False, "message": "Movimiento bancario no encontrado"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            logger.exception("Error al conciliar depósito")
            return Response({"success": False, "message": "No se pudo conciliar el depósito. Verifique los datos."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="pendientes")
    def depositos_pendientes(self, request):
        """
        Obtener depósitos pendientes de conciliación.
        """
        from .models import obtener_depositos_pendientes

        datafono_id = request.query_params.get("datafono_id")
        datafono = None
        if datafono_id:
            try:
                datafono = Datafono.objects.get(id_datafono=datafono_id)
            except Datafono.DoesNotExist:
                return Response(
                    {"success": False, "message": "Datafono no encontrado"}, status=status.HTTP_404_NOT_FOUND
                )

        depositos = obtener_depositos_pendientes(datafono)
        serializer = self.get_serializer(depositos, many=True)

        return Response({"success": True, "depositos": serializer.data}, status=status.HTTP_200_OK)


class CajaFisicaViewSet(BaseModelViewSet):
    queryset = CajaFisica.objects.all()
    serializer_class = CajaFisicaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtrar por empresas del usuario, salvo que sea superusuario
        user = self.request.user
        if not getattr(user, "es_superusuario_omni", False):
            empresas_usuario = getattr(user, "empresas", None)
            if empresas_usuario and hasattr(empresas_usuario, "all"):
                queryset = queryset.filter(empresa__in=empresas_usuario.all())
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
            return Response({"error": str(exc)}, status=400)
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
        sesion = SesionCajaFisica.abrir_sesion(
            caja_fisica=caja,
            usuario=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:1000] or None,
        )
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
            return Response({"error": str(exc)}, status=400)
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

    def perform_create(self, serializer):
        # BUG-C2: los side-effects financieros (TransaccionFinanciera +
        # MovimientoCajaBanco + saldos) van en la MISMA transacción que el
        # Pago (R-CODE-11); el service aplica select_for_update sobre la
        # caja/cuenta afectada.
        from django.db import transaction

        from .services import registrar_efectos_pago

        with transaction.atomic():
            pago = serializer.save()
            registrar_efectos_pago(pago)

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
                        "numero_factura": str(pago.id_documento),
                    },
                )
            except Exception:  # noqa: BLE001
                pass  # notificación best-effort

    def get_queryset(self):
        # R-CODE-1: usar get_empresas_visible para incluir subsidiarias y
        # garantizar aislamiento simétrico con los demás módulos.
        from apps.core.viewsets import get_empresas_visible

        return Pago.objects.filter(id_empresa__in=get_empresas_visible(self.request.user)).order_by("-fecha_pago")

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

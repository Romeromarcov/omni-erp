from django.db import models
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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


class SesionCajaFisicaViewSet(viewsets.ModelViewSet):
    queryset = SesionCajaFisica.objects.all()
    serializer_class = SesionCajaFisicaSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Usar el método de clase para abrir sesión con validaciones
        caja_fisica_id = self.request.data.get("caja_fisica_principal")
        if not caja_fisica_id:
            raise serializers.ValidationError(
                {"caja_fisica_principal": "Debe especificar la caja física para abrir la sesión"}
            )

        from .models import Caja

        try:
            caja_fisica = Caja.objects.get(id_caja=caja_fisica_id, es_fisica=True, activa=True)
        except Caja.DoesNotExist:
            raise serializers.ValidationError({"caja_fisica_principal": "Caja física no encontrada o no válida"})

        observaciones = self.request.data.get("observaciones")
        # Por defecto, usar el nuevo sistema de cajas virtuales automáticas
        cargar_plantillas = self.request.data.get(
            "cargar_plantillas_predeterminadas", False
        )  # Cambiado a False por defecto
        cargar_automaticas = self.request.data.get("cargar_cajas_automaticas", True)  # Nuevo sistema por defecto

        instance = SesionCajaFisica.abrir_sesion(
            usuario=self.request.user,
            caja_fisica=caja_fisica,
            observaciones=observaciones,
            cargar_plantillas_predeterminadas=cargar_plantillas,
        )

        # Si se solicita cargar cajas automáticas, forzar la carga
        if cargar_automaticas:
            instance.cargar_plantillas_predeterminadas()  # Ahora carga las automáticas

    @action(detail=True, methods=["post"], url_path="cerrar")
    def cerrar_sesion(self, request, pk=None):
        """
        Cierra la sesión de caja, realiza el cierre de todas las cajas asociadas y retorna el reporte.
        """
        sesion = self.get_object()
        saldos_reales = request.data.get("saldos_reales", {})
        hasta = request.data.get("hasta")
        usuario = request.user if request.user.is_authenticated else None
        resultados = sesion.cerrar_sesion(saldos_reales=saldos_reales, usuario=usuario, hasta=hasta)
        return Response({"sesion": SesionCajaFisicaSerializer(sesion).data, "cierres": resultados})

    @action(detail=True, methods=["post"], url_path="transferir-entre-cajas")
    def transferir_entre_cajas(self, request, pk=None):
        """
        Permite transferir saldo de una caja origen a una caja destino tras el cierre de sesión.
        """
        from apps.finanzas.utils_transferencias import transferencia_entre_cajas

        sesion = self.get_object()
        caja_origen_id = request.data.get("caja_origen")
        caja_destino_id = request.data.get("caja_destino")
        monto = request.data.get("monto")
        usuario = request.user if request.user.is_authenticated else None
        if not (caja_origen_id and caja_destino_id and monto):
            return Response({"error": "Debe indicar caja_origen, caja_destino y monto."}, status=400)
        try:
            caja_origen = sesion.cajas.get(id_caja=caja_origen_id)
            caja_destino = sesion.cajas.get(id_caja=caja_destino_id)
        except Exception:
            return Response({"error": "Caja origen o destino no pertenece a la sesión."}, status=400)
        mov_salida, mov_entrada = transferencia_entre_cajas(caja_origen, caja_destino, monto, usuario=usuario)
        return Response(
            {
                "movimiento_salida_id": mov_salida.id_movimiento,
                "movimiento_entrada_id": mov_entrada.id_movimiento,
                "caja_origen": str(caja_origen),
                "caja_destino": str(caja_destino),
                "monto": monto,
            }
        )


from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Datafono


class DatafonoViewSet(BaseModelViewSet):
    queryset = Datafono.objects.all()
    # serializer_class = DatafonoSerializer  # Si tienes un serializer, descomenta esto

    @action(detail=True, methods=["post"], url_path="cierre")
    def cierre_datafono(self, request, pk=None):
        """
        Endpoint para realizar el cierre manual de un datafono.
        Permite pasar una fecha/hora límite opcional (hasta) y usa el usuario autenticado.
        """
        datafono = self.get_object()
        hasta = request.data.get("hasta")
        usuario = request.user if request.user.is_authenticated else None
        from django.utils.dateparse import parse_datetime

        hasta_dt = parse_datetime(hasta) if hasta else None
        try:
            resultado = datafono.realizar_cierre(usuario=usuario, hasta=hasta_dt)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)


# ViewSet para MetodoPagoEmpresaActiva
from rest_framework import permissions, viewsets

from .models import MetodoPagoEmpresaActiva
from .serializers import MetodoPagoEmpresaActivaSerializer


class MetodoPagoEmpresaActivaViewSet(viewsets.ModelViewSet):
    queryset = MetodoPagoEmpresaActiva.objects.all()
    serializer_class = MetodoPagoEmpresaActivaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        empresa = self.request.query_params.get("empresa")
        metodo_pago = self.request.query_params.get("metodo_pago")
        if empresa:
            qs = qs.filter(empresa=empresa)
        if metodo_pago:
            qs = qs.filter(metodo_pago=metodo_pago)
        return qs


from django.db import models
from rest_framework import permissions, viewsets

from apps.tesoreria.serializers import CajaSerializer

from .models import (
    Caja,
    CajaUsuario,
    CuentaBancariaEmpresa,
    MetodoPago,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    TasaCambio,
    TransaccionFinanciera,
)
from .serializers import (
    CajaUsuarioSerializer,
    CuentaBancariaEmpresaSerializer,
    MetodoPagoSerializer,
    MonedaEmpresaActivaSerializer,
    MonedaSerializer,
    MovimientoCajaBancoSerializer,
    TasaCambioSerializer,
    TransaccionFinancieraSerializer,
)


class MonedaViewSet(BaseModelViewSet):
    from rest_framework.decorators import action
    from rest_framework.response import Response

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


from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import Empresa


class MetodoPagoViewSet(BaseModelViewSet):

    def get_object(self):
        # Permitir reutilizar métodos de pago de cualquier empresa
        if hasattr(self, "action") and self.action == "reutilizar":
            return MetodoPago.objects.get(id_metodo_pago=self.kwargs[self.lookup_field])
        return super().get_object()

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
        Devuelve métodos de pago reutilizables (de otras empresas, genéricos o públicos) para la empresa actual.
        Marca con 'aplicado' los que ya están en la empresa actual (por nombre y tipo).
        """
        id_empresa_actual = request.query_params.get("id_empresa_actual")
        empresas_excluir = []
        if id_empresa_actual:
            empresas_excluir.append(id_empresa_actual)
        queryset = MetodoPago.objects.filter(
            models.Q(es_generico=True)
            | models.Q(es_publico=True)
            | (~models.Q(empresa__in=empresas_excluir) & ~models.Q(empresa=None))
        )
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
            serializer = self.get_serializer(page, many=True, context=serializer_context)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context=serializer_context)
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
        try:
            empresa = Empresa.objects.get(id_empresa=id_empresa)
        except Empresa.DoesNotExist:
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
            from apps.core.models import Empresa

            empresa = Empresa.objects.filter(id_empresa=empresa_id).first()
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
        # El serializer ya crea el MovimientoCajaBanco automáticamente
        serializer.save()

    def get_queryset(self):
        user = self.request.user
        # Superusuario ve todas
        if getattr(user, "es_superusuario_omni", False):
            return TransaccionFinanciera.objects.all()
        empresas_usuario = user.empresas.all()
        # Filtrar por empresa si se pasa id_empresa como query param
        id_empresa = self.request.query_params.get("id_empresa")
        qs = TransaccionFinanciera.objects.all()
        if id_empresa:
            qs = qs.filter(empresa_id=id_empresa)
        elif empresas_usuario.exists():
            qs = qs.filter(empresa_id__in=empresas_usuario.values_list("id_empresa", flat=True))
        return qs


class MovimientoCajaBancoViewSet(BaseModelViewSet):
    queryset = MovimientoCajaBanco.objects.all()
    serializer_class = MovimientoCajaBancoSerializer


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
        Endpoint para realizar el cierre de una caja.
        Recibe el saldo real contado y opcionalmente una fecha/hora límite.
        """
        from django.utils.dateparse import parse_datetime

        caja = self.get_object()
        saldo_real = request.data.get("saldo_real")
        hasta = request.data.get("hasta")
        usuario = request.user if request.user.is_authenticated else None
        if saldo_real is None:
            return Response({"error": "Debe enviar el saldo_real contado."}, status=400)
        hasta_dt = parse_datetime(hasta) if hasta else None
        try:
            resultado = caja.realizar_cierre(saldo_real=saldo_real, usuario=usuario, hasta=hasta_dt)
        except Exception as e:
            return Response({"error": str(e)}, status=400)
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
        caja_id = pk
        qs = MovimientoCajaBanco.objects.filter(id_caja=caja_id)
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
    from rest_framework.decorators import action
    from rest_framework.response import Response

    from .models import MovimientoCajaBanco
    from .serializers import MovimientoCajaBancoSerializer

    @action(detail=True, methods=["get"], url_path="movimientos-cuenta-bancaria")
    def movimientos_cuenta_bancaria(self, request, pk=None):
        """
        Devuelve los movimientos de la cuenta bancaria asociados a esta cuenta.
        Permite filtrar por fecha, tipo, moneda, concepto, referencia, usuario.
        """
        cuenta_id = pk
        qs = MovimientoCajaBanco.objects.filter(id_cuenta_bancaria=cuenta_id)
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
class CajaUsuarioViewSet(viewsets.ModelViewSet):
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
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ViewSet para CajaVirtualUsuario
class CajaVirtualUsuarioViewSet(viewsets.ModelViewSet):
    queryset = CajaVirtualUsuario.objects.all()
    serializer_class = CajaVirtualUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filtra las cajas virtuales asignadas al usuario actual.
        """
        return CajaVirtualUsuario.objects.filter(usuario=self.request.user).select_related("caja_virtual")


# ViewSet para CajaFisicaUsuario
class CajaFisicaUsuarioViewSet(viewsets.ModelViewSet):
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


from .models import PlantillaMaestroCajasVirtuales
from .serializers import PlantillaMaestroCajasVirtualesSerializer


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
        queryset = super().get_queryset()
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
        except ValueError as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
        except ValueError as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
        except ValueError as e:
            return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

    def perform_create(self, serializer):
        """Crear el pago y generar la transacción financiera correspondiente"""
        pago = serializer.save()

        # Crear transacción financiera
        from .models import TransaccionFinanciera

        transaccion = TransaccionFinanciera.objects.create(
            id_empresa=pago.id_empresa,
            fecha_hora_transaccion=pago.fecha_pago,
            tipo_transaccion=pago.tipo_operacion,
            monto_transaccion=pago.monto,
            id_moneda_transaccion=pago.id_moneda,
            id_moneda_base=pago.id_moneda,  # Simplificación
            monto_base_empresa=pago.monto,
            id_metodo_pago=pago.id_metodo_pago,
            referencia_pago=pago.referencia,
            descripcion=f"Pago {pago.tipo_operacion.lower()} - {pago.get_tipo_documento_display()}",
            tipo_documento_asociado=pago.tipo_documento,
            nro_documento_asociado=str(pago.id_documento),
            id_caja=pago.id_caja_virtual,
            id_cuenta_bancaria=pago.id_cuenta_bancaria,
            id_usuario_registro=pago.id_usuario_registro,
        )

        # Asociar la transacción financiera al pago
        pago.id_transaccion_financiera = transaccion
        pago.save(update_fields=["id_transaccion_financiera"])

        # Si es pago con tarjeta, crear TransaccionDatafono
        if pago.id_datafono:
            from .models import TransaccionDatafono

            TransaccionDatafono.objects.create(
                id_datafono=pago.id_datafono,
                monto=pago.monto,
                referencia_bancaria=pago.referencia,
                id_transaccion_financiera_origen=transaccion,  # Usar la transacción ya creada
                id_usuario_registro=pago.id_usuario_registro,
            )

        # Crear movimiento de caja/banco si corresponde
        if pago.id_caja_virtual or pago.id_cuenta_bancaria:
            saldo_anterior = 0
            if pago.id_caja_virtual:
                saldo_anterior = pago.id_caja_virtual.saldo_actual
            elif pago.id_cuenta_bancaria:
                saldo_anterior = pago.id_cuenta_bancaria.saldo_actual

            # Determinar el tipo de movimiento (INGRESO/EGRESO)
            tipo_movimiento = "INGRESO" if pago.tipo_operacion == "INGRESO" else "EGRESO"

            from .models import MovimientoCajaBanco

            movimiento = MovimientoCajaBanco.objects.create(
                id_empresa=pago.id_empresa,
                fecha_movimiento=pago.fecha_pago.date(),
                hora_movimiento=pago.fecha_pago.time(),
                tipo_movimiento=tipo_movimiento,
                monto=pago.monto,
                id_moneda=pago.id_moneda,
                concepto=f"{pago.tipo_operacion} - {pago.get_tipo_documento_display()}",
                referencia=pago.referencia or f"Pago {pago.id_pago}",
                id_caja=pago.id_caja_virtual,
                id_cuenta_bancaria=pago.id_cuenta_bancaria,
                saldo_anterior=saldo_anterior,
                saldo_nuevo=saldo_anterior + (pago.monto if tipo_movimiento == "INGRESO" else -pago.monto),
                id_usuario_registro=pago.id_usuario_registro,
            )

            # Actualizar saldo
            if pago.id_caja_virtual:
                pago.id_caja_virtual.saldo_actual = movimiento.saldo_nuevo
                pago.id_caja_virtual.save()
            elif pago.id_cuenta_bancaria:
                pago.id_cuenta_bancaria.saldo_actual = movimiento.saldo_nuevo
                pago.id_cuenta_bancaria.save()

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

    @action(detail=False, methods=["get"], url_path="tipo-caja-choices", permission_classes=[])
    def tipo_caja_choices(self, request):
        """
        Devuelve las opciones disponibles para el campo tipo_caja.
        """
        from .models import CajaFisica

        return Response([{"value": value, "display": display} for value, display in CajaFisica.TIPO_CAJA_CHOICES])


class PagoViewSet(BaseModelViewSet):
    queryset = Pago.objects.all()
    serializer_class = PagoSerializer

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

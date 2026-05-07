from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count
from .models import CategoriaGasto, Gasto, ReembolsoGasto
from .serializers import CategoriaGastoSerializer, GastoSerializer, ReembolsoGastoSerializer

class CategoriaGastoViewSet(viewsets.ModelViewSet):
    queryset = CategoriaGasto.objects.all()
    serializer_class = CategoriaGastoSerializer
    filterset_fields = ['activo', 'id_empresa']
    search_fields = ['nombre_categoria', 'descripcion']
    ordering_fields = ['nombre_categoria', 'fecha_creacion']
    ordering = ['nombre_categoria']

    @action(detail=False, methods=['get'])
    def activas(self, request):
        """Obtiene solo las categorías activas"""
        categorias_activas = self.queryset.filter(activo=True)
        serializer = self.get_serializer(categorias_activas, many=True)
        return Response(serializer.data)

class GastoViewSet(viewsets.ModelViewSet):
    queryset = Gasto.objects.all()
    serializer_class = GastoSerializer
    filterset_fields = ['estado_gasto', 'id_empresa', 'id_categoria_gasto', 'fecha_gasto']
    search_fields = ['descripcion']
    ordering_fields = ['fecha_gasto', 'monto', 'fecha_creacion']
    ordering = ['-fecha_gasto']

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Aprueba un gasto"""
        gasto = self.get_object()
        
        if gasto.estado_gasto != 'PENDIENTE_APROBACION':
            return Response(
                {'error': 'Solo se pueden aprobar gastos pendientes de aprobación'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        gasto.estado_gasto = 'APROBADO'
        gasto.save()
        
        serializer = self.get_serializer(gasto)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        """Rechaza un gasto"""
        gasto = self.get_object()
        
        if gasto.estado_gasto != 'PENDIENTE_APROBACION':
            return Response(
                {'error': 'Solo se pueden rechazar gastos pendientes de aprobación'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        gasto.estado_gasto = 'RECHAZADO'
        gasto.save()
        
        serializer = self.get_serializer(gasto)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def resumen_por_categoria(self, request):
        """Obtiene resumen de gastos por categoría"""
        empresa_id = request.query_params.get('empresa_id')
        if not empresa_id:
            return Response(
                {'error': 'Debe especificar el ID de la empresa'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        gastos = self.queryset.filter(
            id_empresa=empresa_id,
            estado_gasto__in=['APROBADO', 'REEMBOLSADO', 'CONTABILIZADO']
        ).select_related('id_categoria_gasto')
        
        # Agrupar por categoría
        resumen = {}
        for gasto in gastos:
            categoria_id = str(gasto.id_categoria_gasto.id_categoria_gasto)
            if categoria_id not in resumen:
                resumen[categoria_id] = {
                    'categoria_nombre': gasto.id_categoria_gasto.nombre_categoria,
                    'total_gastos': 0,
                    'cantidad_gastos': 0
                }
            
            resumen[categoria_id]['total_gastos'] += gasto.monto
            resumen[categoria_id]['cantidad_gastos'] += 1
        
        return Response({
            'empresa_id': empresa_id,
            'resumen_por_categoria': list(resumen.values()),
            'total_general': sum(r['total_gastos'] for r in resumen.values())
        })

    @action(detail=False, methods=['get'])
    def pendientes_aprobacion(self, request):
        """Obtiene gastos pendientes de aprobación"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'estado_gasto': 'PENDIENTE_APROBACION'}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        gastos_pendientes = self.queryset.filter(**filters)
        serializer = self.get_serializer(gastos_pendientes, many=True)
        return Response(serializer.data)

class ReembolsoGastoViewSet(viewsets.ModelViewSet):
    queryset = ReembolsoGasto.objects.all()
    serializer_class = ReembolsoGastoSerializer
    filterset_fields = ['estado_reembolso', 'id_empresa', 'fecha_reembolso']
    search_fields = ['id_gasto__descripcion']
    ordering_fields = ['fecha_reembolso', 'monto_reembolso', 'fecha_creacion']
    ordering = ['-fecha_reembolso']

    @action(detail=True, methods=['post'])
    def procesar_pago(self, request, pk=None):
        """Procesa el pago de un reembolso"""
        reembolso = self.get_object()
        
        if reembolso.estado_reembolso != 'PENDIENTE':
            return Response(
                {'error': 'Solo se pueden procesar reembolsos pendientes'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reembolso.estado_reembolso = 'PAGADO'
        reembolso.save()
        
        # También actualizar el estado del gasto asociado
        gasto = reembolso.id_gasto
        if gasto.estado_gasto == 'APROBADO':
            gasto.estado_gasto = 'REEMBOLSADO'
            gasto.save()
        
        serializer = self.get_serializer(reembolso)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        """Anula un reembolso"""
        reembolso = self.get_object()
        
        if reembolso.estado_reembolso == 'PAGADO':
            return Response(
                {'error': 'No se puede anular un reembolso ya pagado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reembolso.estado_reembolso = 'ANULADO'
        reembolso.save()
        
        serializer = self.get_serializer(reembolso)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pendientes_pago(self, request):
        """Obtiene reembolsos pendientes de pago"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'estado_reembolso': 'PENDIENTE'}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        reembolsos_pendientes = self.queryset.filter(**filters)
        serializer = self.get_serializer(reembolsos_pendientes, many=True)
        return Response(serializer.data)

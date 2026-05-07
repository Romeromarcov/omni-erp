from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count
from django.utils import timezone
from .models import (
    PeriodoNomina, ConceptoNomina, ProcesoNomina, Nomina, DetalleNomina,
    ProcesoNominaExtrasalarial, NominaExtrasalarial
)
from .serializers import (
    PeriodoNominaSerializer, ConceptoNominaSerializer, ProcesoNominaSerializer,
    NominaSerializer, DetalleNominaSerializer, ProcesoNominaExtrasalarialSerializer,
    NominaExtrasalarialSerializer
)

class PeriodoNominaViewSet(viewsets.ModelViewSet):
    queryset = PeriodoNomina.objects.all()
    serializer_class = PeriodoNominaSerializer
    filterset_fields = ['estado', 'tipo_periodo', 'id_empresa', 'activo']
    search_fields = ['nombre_periodo']
    ordering_fields = ['fecha_inicio', 'fecha_fin', 'fecha_pago', 'nombre_periodo']
    ordering = ['-fecha_inicio']

    @action(detail=False, methods=['get'])
    def activos(self, request):
        """Obtiene períodos activos"""
        periodos_activos = self.queryset.filter(activo=True)
        serializer = self.get_serializer(periodos_activos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def abiertos(self, request):
        """Obtiene períodos en estado abierto"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'estado': 'ABIERTO', 'activo': True}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        periodos_abiertos = self.queryset.filter(**filters)
        serializer = self.get_serializer(periodos_abiertos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        """Cierra un período de nómina"""
        periodo = self.get_object()
        
        if periodo.estado != 'ABIERTO':
            return Response(
                {'error': 'Solo se pueden cerrar períodos en estado abierto'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        periodo.estado = 'CERRADO'
        periodo.save()
        
        serializer = self.get_serializer(periodo)
        return Response(serializer.data)

class ConceptoNominaViewSet(viewsets.ModelViewSet):
    queryset = ConceptoNomina.objects.all()
    serializer_class = ConceptoNominaSerializer
    filterset_fields = ['tipo_concepto', 'categoria', 'activo', 'id_empresa', 'es_fijo', 'es_porcentaje']
    search_fields = ['codigo_concepto', 'nombre_concepto']
    ordering_fields = ['codigo_concepto', 'nombre_concepto', 'fecha_creacion']
    ordering = ['codigo_concepto']

    @action(detail=False, methods=['get'])
    def por_tipo(self, request):
        """Obtiene conceptos filtrados por tipo"""
        tipo = request.query_params.get('tipo')
        empresa_id = request.query_params.get('empresa_id')
        
        filters = {'activo': True}
        if tipo:
            filters['tipo_concepto'] = tipo
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        conceptos = self.queryset.filter(**filters)
        serializer = self.get_serializer(conceptos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def devengados(self, request):
        """Obtiene conceptos de tipo devengado"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'tipo_concepto': 'DEVENGADO', 'activo': True}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        conceptos = self.queryset.filter(**filters)
        serializer = self.get_serializer(conceptos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def deducciones(self, request):
        """Obtiene conceptos de tipo deducción"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'tipo_concepto': 'DEDUCCION', 'activo': True}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        conceptos = self.queryset.filter(**filters)
        serializer = self.get_serializer(conceptos, many=True)
        return Response(serializer.data)

class ProcesoNominaViewSet(viewsets.ModelViewSet):
    queryset = ProcesoNomina.objects.all()
    serializer_class = ProcesoNominaSerializer
    filterset_fields = ['estado', 'id_empresa', 'id_periodo_nomina']
    search_fields = ['numero_proceso']
    ordering_fields = ['fecha_proceso', 'numero_proceso', 'total_neto']
    ordering = ['-fecha_proceso']

    @action(detail=True, methods=['post'])
    def procesar(self, request, pk=None):
        """Inicia el procesamiento de nómina"""
        proceso = self.get_object()
        
        if proceso.estado != 'EN_PROCESO':
            return Response(
                {'error': 'El proceso ya ha sido completado o cancelado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Aquí iría la lógica de procesamiento de nómina
        proceso.estado = 'COMPLETADO'
        proceso.fecha_proceso = timezone.now()
        proceso.save()
        
        serializer = self.get_serializer(proceso)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Aprueba un proceso de nómina"""
        proceso = self.get_object()
        
        if proceso.estado != 'COMPLETADO':
            return Response(
                {'error': 'Solo se pueden aprobar procesos completados'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        proceso.estado = 'APROBADO'
        proceso.save()
        
        # Actualizar estado de nóminas asociadas
        Nomina.objects.filter(id_proceso_nomina=proceso, estado='CALCULADA').update(
            estado='APROBADA'
        )
        
        serializer = self.get_serializer(proceso)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def resumen(self, request, pk=None):
        """Obtiene resumen del proceso de nómina"""
        proceso = self.get_object()
        nominas = proceso.nominas.all()
        
        resumen = {
            'total_empleados': nominas.count(),
            'total_devengado': nominas.aggregate(Sum('total_devengado'))['total_devengado__sum'] or 0,
            'total_deducciones': nominas.aggregate(Sum('total_deducciones'))['total_deducciones__sum'] or 0,
            'total_neto': nominas.aggregate(Sum('total_neto'))['total_neto__sum'] or 0,
            'promedio_sueldo': nominas.aggregate(Sum('sueldo_base'))['sueldo_base__sum'] or 0 / max(nominas.count(), 1)
        }
        
        return Response(resumen)

class NominaViewSet(viewsets.ModelViewSet):
    queryset = Nomina.objects.all()
    serializer_class = NominaSerializer
    filterset_fields = ['estado', 'id_proceso_nomina', 'id_empleado']
    search_fields = ['id_empleado__nombre', 'id_empleado__apellido']
    ordering_fields = ['fecha_calculo', 'total_neto', 'sueldo_base']
    ordering = ['-fecha_calculo']

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Aprueba una nómina individual"""
        nomina = self.get_object()
        
        if nomina.estado != 'CALCULADA':
            return Response(
                {'error': 'Solo se pueden aprobar nóminas calculadas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        nomina.estado = 'APROBADA'
        nomina.save()
        
        serializer = self.get_serializer(nomina)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def marcar_pagada(self, request, pk=None):
        """Marca una nómina como pagada"""
        nomina = self.get_object()
        
        if nomina.estado != 'APROBADA':
            return Response(
                {'error': 'Solo se pueden marcar como pagadas nóminas aprobadas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        nomina.estado = 'PAGADA'
        nomina.save()
        
        serializer = self.get_serializer(nomina)
        return Response(serializer.data)

class DetalleNominaViewSet(viewsets.ModelViewSet):
    queryset = DetalleNomina.objects.all()
    serializer_class = DetalleNominaSerializer
    filterset_fields = ['id_nomina', 'id_concepto_nomina']
    ordering_fields = ['valor_total']
    ordering = ['id_concepto_nomina__codigo_concepto']

class ProcesoNominaExtrasalarialViewSet(viewsets.ModelViewSet):
    queryset = ProcesoNominaExtrasalarial.objects.all()
    serializer_class = ProcesoNominaExtrasalarialSerializer
    filterset_fields = ['estado', 'tipo_proceso', 'id_empresa']
    search_fields = ['numero_proceso']
    ordering_fields = ['fecha_proceso', 'total_monto']
    ordering = ['-fecha_proceso']

    @action(detail=True, methods=['post'])
    def procesar(self, request, pk=None):
        """Procesa nómina extrasalarial"""
        proceso = self.get_object()
        
        if proceso.estado != 'EN_PROCESO':
            return Response(
                {'error': 'El proceso ya ha sido completado o cancelado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        proceso.estado = 'COMPLETADO'
        proceso.save()
        
        serializer = self.get_serializer(proceso)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Aprueba proceso extrasalarial"""
        proceso = self.get_object()
        
        if proceso.estado != 'COMPLETADO':
            return Response(
                {'error': 'Solo se pueden aprobar procesos completados'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        proceso.estado = 'APROBADO'
        proceso.save()
        
        # Actualizar nóminas extrasalariales asociadas
        NominaExtrasalarial.objects.filter(
            id_proceso_extrasalarial=proceso, 
            estado='CALCULADA'
        ).update(estado='APROBADA')
        
        serializer = self.get_serializer(proceso)
        return Response(serializer.data)

class NominaExtrasalarialViewSet(viewsets.ModelViewSet):
    queryset = NominaExtrasalarial.objects.all()
    serializer_class = NominaExtrasalarialSerializer
    filterset_fields = ['estado', 'id_proceso_extrasalarial', 'id_empleado']
    search_fields = ['id_empleado__nombre', 'id_empleado__apellido']
    ordering_fields = ['fecha_calculo', 'monto_neto']
    ordering = ['-fecha_calculo']

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Aprueba nómina extrasalarial"""
        nomina = self.get_object()
        
        if nomina.estado != 'CALCULADA':
            return Response(
                {'error': 'Solo se pueden aprobar nóminas calculadas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        nomina.estado = 'APROBADA'
        nomina.save()
        
        serializer = self.get_serializer(nomina)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def marcar_pagada(self, request, pk=None):
        """Marca nómina extrasalarial como pagada"""
        nomina = self.get_object()
        
        if nomina.estado != 'APROBADA':
            return Response(
                {'error': 'Solo se pueden marcar como pagadas nóminas aprobadas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        nomina.estado = 'PAGADA'
        nomina.save()
        
        serializer = self.get_serializer(nomina)
        return Response(serializer.data)

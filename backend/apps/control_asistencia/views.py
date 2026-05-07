from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import HorarioTrabajo, AsignacionHorario, RegistroAsistencia, ResumenAsistenciaDiario
from .serializers import (
    HorarioTrabajoSerializer, AsignacionHorarioSerializer,
    RegistroAsistenciaSerializer, ResumenAsistenciaDiarioSerializer
)

class HorarioTrabajoViewSet(viewsets.ModelViewSet):
    queryset = HorarioTrabajo.objects.all()
    serializer_class = HorarioTrabajoSerializer
    filterset_fields = ['activo', 'id_empresa']
    search_fields = ['nombre_horario', 'descripcion']
    ordering_fields = ['nombre_horario', 'total_horas_semanales']
    ordering = ['nombre_horario']

    @action(detail=False, methods=['get'])
    def activos(self, request):
        """Obtiene horarios activos"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'activo': True}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        horarios_activos = self.queryset.filter(**filters)
        serializer = self.get_serializer(horarios_activos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def desactivar(self, request, pk=None):
        """Desactiva un horario de trabajo"""
        horario = self.get_object()
        
        # Verificar si hay asignaciones activas
        asignaciones_activas = AsignacionHorario.objects.filter(
            id_horario=horario,
            activo=True
        ).count()
        
        if asignaciones_activas > 0:
            return Response(
                {'error': f'No se puede desactivar. Hay {asignaciones_activas} asignaciones activas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        horario.activo = False
        horario.save()
        
        serializer = self.get_serializer(horario)
        return Response(serializer.data)

class AsignacionHorarioViewSet(viewsets.ModelViewSet):
    queryset = AsignacionHorario.objects.all()
    serializer_class = AsignacionHorarioSerializer
    filterset_fields = ['activo', 'id_empleado_temp', 'id_horario']
    ordering_fields = ['fecha_inicio', 'fecha_fin']
    ordering = ['-fecha_inicio']

    @action(detail=False, methods=['get'])
    def activas(self, request):
        """Obtiene asignaciones activas"""
        empleado_id = request.query_params.get('empleado_id')
        filters = {'activo': True}
        if empleado_id:
            filters['id_empleado_temp'] = empleado_id
            
        asignaciones_activas = self.queryset.filter(**filters)
        serializer = self.get_serializer(asignaciones_activas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def por_empleado(self, request):
        """Obtiene asignaciones por empleado"""
        empleado_id = request.query_params.get('empleado_id')
        if not empleado_id:
            return Response(
                {'error': 'Debe especificar el ID del empleado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        asignaciones = self.queryset.filter(id_empleado_temp=empleado_id)
        serializer = self.get_serializer(asignaciones, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def finalizar(self, request, pk=None):
        """Finaliza una asignación de horario"""
        asignacion = self.get_object()
        
        if not asignacion.activo:
            return Response(
                {'error': 'La asignación ya está finalizada'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        fecha_fin = request.data.get('fecha_fin')
        if not fecha_fin:
            fecha_fin = timezone.now().date()
        
        asignacion.fecha_fin = fecha_fin
        asignacion.activo = False
        asignacion.save()
        
        serializer = self.get_serializer(asignacion)
        return Response(serializer.data)

class RegistroAsistenciaViewSet(viewsets.ModelViewSet):
    queryset = RegistroAsistencia.objects.all()
    serializer_class = RegistroAsistenciaSerializer
    filterset_fields = ['id_empleado_temp', 'tipo_marcado', 'metodo_marcado']
    search_fields = ['observaciones']
    ordering_fields = ['fecha_hora_marcado']
    ordering = ['-fecha_hora_marcado']

    @action(detail=False, methods=['post'])
    def marcar_asistencia(self, request):
        """Registra un marcado de asistencia"""
        empleado_id = request.data.get('empleado_id')
        tipo_marcado = request.data.get('tipo_marcado')
        metodo_marcado = request.data.get('metodo_marcado', 'WEB')
        ubicacion_gps = request.data.get('ubicacion_gps')
        observaciones = request.data.get('observaciones')
        
        if not empleado_id or not tipo_marcado:
            return Response(
                {'error': 'Empleado y tipo de marcado son requeridos'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Crear registro de asistencia
        registro = RegistroAsistencia.objects.create(
            id_empleado_temp=empleado_id,
            fecha_hora_marcado=timezone.now(),
            tipo_marcado=tipo_marcado,
            metodo_marcado=metodo_marcado,
            ubicacion_gps_json=ubicacion_gps,
            observaciones=observaciones
        )
        
        serializer = self.get_serializer(registro)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def por_empleado_fecha(self, request):
        """Obtiene registros por empleado y rango de fechas"""
        empleado_id = request.query_params.get('empleado_id')
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin = request.query_params.get('fecha_fin')
        
        if not empleado_id:
            return Response(
                {'error': 'Debe especificar el ID del empleado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        filters = {'id_empleado_temp': empleado_id}
        
        if fecha_inicio:
            filters['fecha_hora_marcado__date__gte'] = fecha_inicio
        if fecha_fin:
            filters['fecha_hora_marcado__date__lte'] = fecha_fin
        
        registros = self.queryset.filter(**filters)
        serializer = self.get_serializer(registros, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def hoy(self, request):
        """Obtiene registros del día actual"""
        empleado_id = request.query_params.get('empleado_id')
        hoy = timezone.now().date()
        
        filters = {'fecha_hora_marcado__date': hoy}
        if empleado_id:
            filters['id_empleado_temp'] = empleado_id
        
        registros = self.queryset.filter(**filters)
        serializer = self.get_serializer(registros, many=True)
        return Response(serializer.data)

class ResumenAsistenciaDiarioViewSet(viewsets.ModelViewSet):
    queryset = ResumenAsistenciaDiario.objects.all()
    serializer_class = ResumenAsistenciaDiarioSerializer
    filterset_fields = ['id_empleado_temp', 'fecha', 'es_ausencia', 'estado_revision']
    ordering_fields = ['fecha', 'horas_trabajadas_netas']
    ordering = ['-fecha']

    @action(detail=False, methods=['post'])
    def generar_resumen_diario(self, request):
        """Genera resumen diario de asistencia para una fecha específica"""
        fecha = request.data.get('fecha')
        empleado_id = request.data.get('empleado_id')
        
        if not fecha:
            fecha = timezone.now().date()
        
        # Si se especifica empleado, procesar solo ese empleado
        if empleado_id:
            empleados_ids = [empleado_id]
        else:
            # Obtener todos los empleados que tienen registros de asistencia en la fecha
            empleados_ids = RegistroAsistencia.objects.filter(
                fecha_hora_marcado__date=fecha
            ).values_list('id_empleado_temp', flat=True).distinct()
        
        resumenes_creados = 0
        
        for empleado_id in empleados_ids:
            # Verificar si ya existe resumen para esta fecha y empleado
            resumen_existente = ResumenAsistenciaDiario.objects.filter(
                id_empleado_temp=empleado_id,
                fecha=fecha
            ).first()
            
            if resumen_existente:
                continue
            
            # Obtener registros de asistencia del empleado para la fecha
            registros = RegistroAsistencia.objects.filter(
                id_empleado_temp=empleado_id,
                fecha_hora_marcado__date=fecha
            ).order_by('fecha_hora_marcado')
            
            if not registros.exists():
                # Crear resumen de ausencia
                ResumenAsistenciaDiario.objects.create(
                    id_empleado_temp=empleado_id,
                    fecha=fecha,
                    es_ausencia=True,
                    estado_revision='PENDIENTE'
                )
                resumenes_creados += 1
                continue
            
            # Calcular horas trabajadas
            entrada = None
            salida = None
            
            for registro in registros:
                if registro.tipo_marcado == 'ENTRADA' and not entrada:
                    entrada = registro.fecha_hora_marcado
                elif registro.tipo_marcado == 'SALIDA':
                    salida = registro.fecha_hora_marcado
            
            horas_trabajadas = 0
            if entrada and salida:
                diferencia = salida - entrada
                horas_trabajadas = diferencia.total_seconds() / 3600
            
            # Crear resumen
            ResumenAsistenciaDiario.objects.create(
                id_empleado_temp=empleado_id,
                fecha=fecha,
                hora_entrada_real=entrada.time() if entrada else None,
                hora_salida_real=salida.time() if salida else None,
                horas_trabajadas_netas=horas_trabajadas,
                es_ausencia=False,
                estado_revision='PENDIENTE'
            )
            resumenes_creados += 1
        
        return Response({
            'mensaje': f'Se generaron {resumenes_creados} resúmenes diarios',
            'fecha': fecha
        })

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """Aprueba un resumen de asistencia"""
        resumen = self.get_object()
        
        if resumen.estado_revision == 'APROBADO':
            return Response(
                {'error': 'El resumen ya está aprobado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        resumen.estado_revision = 'APROBADO'
        resumen.observaciones_supervisor = request.data.get('observaciones', '')
        resumen.save()
        
        serializer = self.get_serializer(resumen)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pendientes_revision(self, request):
        """Obtiene resúmenes pendientes de revisión"""
        empleado_id = request.query_params.get('empleado_id')
        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        
        filters = {'estado_revision': 'PENDIENTE'}
        
        if empleado_id:
            filters['id_empleado_temp'] = empleado_id
        if fecha_desde:
            filters['fecha__gte'] = fecha_desde
        if fecha_hasta:
            filters['fecha__lte'] = fecha_hasta
        
        resumenes = self.queryset.filter(**filters)
        serializer = self.get_serializer(resumenes, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def reporte_mensual(self, request):
        """Genera reporte mensual de asistencia"""
        empleado_id = request.query_params.get('empleado_id')
        año = request.query_params.get('año', timezone.now().year)
        mes = request.query_params.get('mes', timezone.now().month)
        
        if not empleado_id:
            return Response(
                {'error': 'Debe especificar el ID del empleado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        resumenes = self.queryset.filter(
            id_empleado_temp=empleado_id,
            fecha__year=año,
            fecha__month=mes
        )
        
        # Calcular estadísticas
        total_dias = resumenes.count()
        dias_trabajados = resumenes.filter(es_ausencia=False).count()
        ausencias = resumenes.filter(es_ausencia=True).count()
        horas_totales = resumenes.aggregate(Sum('horas_trabajadas_netas'))['horas_trabajadas_netas__sum'] or 0
        tardanzas = resumenes.filter(minutos_tardanza__gt=0).count()
        
        return Response({
            'empleado_id': empleado_id,
            'año': año,
            'mes': mes,
            'total_dias': total_dias,
            'dias_trabajados': dias_trabajados,
            'ausencias': ausencias,
            'horas_totales': float(horas_totales),
            'tardanzas': tardanzas,
            'resumenes': self.get_serializer(resumenes, many=True).data
        })

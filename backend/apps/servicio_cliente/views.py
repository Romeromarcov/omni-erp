from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import (
    CategoriaTicket, TicketSoporte, InteraccionTicket, 
    BaseConocimientoArticulo, FeedbackCliente
)
from .serializers import (
    CategoriaTicketSerializer, TicketSoporteSerializer, InteraccionTicketSerializer,
    BaseConocimientoArticuloSerializer, FeedbackClienteSerializer
)

class CategoriaTicketViewSet(viewsets.ModelViewSet):
    queryset = CategoriaTicket.objects.all()
    serializer_class = CategoriaTicketSerializer
    filterset_fields = ['activo', 'id_empresa']
    search_fields = ['nombre_categoria', 'descripcion']
    ordering_fields = ['nombre_categoria']
    ordering = ['nombre_categoria']

    @action(detail=False, methods=['get'])
    def activas(self, request):
        """Obtiene categorías activas"""
        empresa_id = request.query_params.get('empresa_id')
        filters = {'activo': True}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        categorias_activas = self.queryset.filter(**filters)
        serializer = self.get_serializer(categorias_activas, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def estadisticas(self, request, pk=None):
        """Obtiene estadísticas de tickets por categoría"""
        categoria = self.get_object()
        
        tickets_count = TicketSoporte.objects.filter(id_categoria_ticket=categoria).count()
        tickets_abiertos = TicketSoporte.objects.filter(
            id_categoria_ticket=categoria, 
            estado_ticket__in=['ABIERTO', 'ASIGNADO', 'EN_PROGRESO']
        ).count()
        tickets_cerrados = TicketSoporte.objects.filter(
            id_categoria_ticket=categoria, 
            estado_ticket='CERRADO'
        ).count()
        
        return Response({
            'total_tickets': tickets_count,
            'tickets_abiertos': tickets_abiertos,
            'tickets_cerrados': tickets_cerrados,
            'porcentaje_resolucion': (tickets_cerrados / max(tickets_count, 1)) * 100
        })

class TicketSoporteViewSet(viewsets.ModelViewSet):
    queryset = TicketSoporte.objects.all()
    serializer_class = TicketSoporteSerializer
    filterset_fields = [
        'estado_ticket', 'prioridad', 'id_categoria_ticket', 
        'id_empresa', 'id_cliente_temp', 'id_agente_asignado_temp'
    ]
    search_fields = ['numero_ticket', 'asunto', 'descripcion']
    ordering_fields = ['fecha_apertura', 'fecha_ultima_actualizacion', 'prioridad']
    ordering = ['-fecha_apertura']

    @action(detail=False, methods=['get'])
    def abiertos(self, request):
        """Obtiene tickets abiertos"""
        empresa_id = request.query_params.get('empresa_id')
        agente_id = request.query_params.get('agente_id')
        
        filters = {'estado_ticket__in': ['ABIERTO', 'ASIGNADO', 'EN_PROGRESO', 'ESCALADO']}
        if empresa_id:
            filters['id_empresa'] = empresa_id
        if agente_id:
            filters['id_agente_asignado_temp'] = agente_id
            
        tickets_abiertos = self.queryset.filter(**filters)
        serializer = self.get_serializer(tickets_abiertos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def por_prioridad(self, request):
        """Obtiene tickets filtrados por prioridad"""
        prioridad = request.query_params.get('prioridad')
        empresa_id = request.query_params.get('empresa_id')
        
        if not prioridad:
            return Response(
                {'error': 'Debe especificar la prioridad'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        filters = {'prioridad': prioridad}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        tickets = self.queryset.filter(**filters)
        serializer = self.get_serializer(tickets, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def asignar_agente(self, request, pk=None):
        """Asigna un agente a un ticket"""
        ticket = self.get_object()
        agente_id = request.data.get('agente_id')
        
        if not agente_id:
            return Response(
                {'error': 'Debe especificar el ID del agente'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ticket.id_agente_asignado_temp = agente_id
        ticket.estado_ticket = 'ASIGNADO'
        ticket.save()
        
        # Crear interacción de asignación
        InteraccionTicket.objects.create(
            id_ticket=ticket,
            tipo_interaccion='ASIGNACION',
            contenido=f'Ticket asignado al agente {agente_id}',
            id_usuario_interactor_temp=request.user.pk if hasattr(request.user, 'pk') else None
        )
        
        serializer = self.get_serializer(ticket)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cambiar_estado(self, request, pk=None):
        """Cambia el estado de un ticket"""
        ticket = self.get_object()
        nuevo_estado = request.data.get('estado')
        comentario = request.data.get('comentario', '')
        
        estados_validos = [
            'ABIERTO', 'ASIGNADO', 'EN_PROGRESO', 
            'PENDIENTE_CLIENTE', 'RESUELTO', 'CERRADO', 'ESCALADO'
        ]
        
        if nuevo_estado not in estados_validos:
            return Response(
                {'error': f'Estado inválido. Estados válidos: {", ".join(estados_validos)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        estado_anterior = ticket.estado_ticket
        ticket.estado_ticket = nuevo_estado
        
        # Si se cierra el ticket, establecer fecha de cierre
        if nuevo_estado == 'CERRADO':
            ticket.fecha_cierre = timezone.now()
        
        ticket.save()
        
        # Crear interacción de cambio de estado
        InteraccionTicket.objects.create(
            id_ticket=ticket,
            tipo_interaccion='CAMBIO_ESTADO',
            contenido=f'Estado cambiado de {estado_anterior} a {nuevo_estado}. {comentario}',
            id_usuario_interactor_temp=request.user.pk if hasattr(request.user, 'pk') else None
        )
        
        serializer = self.get_serializer(ticket)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def escalar(self, request, pk=None):
        """Escala un ticket"""
        ticket = self.get_object()
        razon = request.data.get('razon', '')
        nuevo_agente_id = request.data.get('nuevo_agente_id')
        
        ticket.estado_ticket = 'ESCALADO'
        ticket.prioridad = 'ALTA'  # Aumentar prioridad al escalar
        
        if nuevo_agente_id:
            ticket.id_agente_asignado_temp = nuevo_agente_id
        
        ticket.save()
        
        # Crear interacción de escalación
        InteraccionTicket.objects.create(
            id_ticket=ticket,
            tipo_interaccion='CAMBIO_ESTADO',
            contenido=f'Ticket escalado. Razón: {razon}',
            id_usuario_interactor_temp=request.user.pk if hasattr(request.user, 'pk') else None
        )
        
        serializer = self.get_serializer(ticket)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Obtiene métricas para dashboard de servicio al cliente"""
        empresa_id = request.query_params.get('empresa_id')
        agente_id = request.query_params.get('agente_id')
        
        filters = {}
        if empresa_id:
            filters['id_empresa'] = empresa_id
        if agente_id:
            filters['id_agente_asignado_temp'] = agente_id
        
        queryset = self.queryset.filter(**filters)
        
        # Métricas generales
        total_tickets = queryset.count()
        tickets_abiertos = queryset.filter(
            estado_ticket__in=['ABIERTO', 'ASIGNADO', 'EN_PROGRESO', 'ESCALADO']
        ).count()
        tickets_cerrados_hoy = queryset.filter(
            estado_ticket='CERRADO',
            fecha_cierre__date=timezone.now().date()
        ).count()
        
        # Tickets por prioridad
        tickets_por_prioridad = queryset.values('prioridad').annotate(
            count=Count('id_ticket')
        )
        
        # Tickets por estado
        tickets_por_estado = queryset.values('estado_ticket').annotate(
            count=Count('id_ticket')
        )
        
        # Tiempo promedio de resolución (últimos 30 días)
        tickets_cerrados_recientes = queryset.filter(
            estado_ticket='CERRADO',
            fecha_cierre__gte=timezone.now() - timedelta(days=30)
        )
        
        tiempo_promedio = 0
        if tickets_cerrados_recientes.exists():
            tiempos_resolucion = []
            for ticket in tickets_cerrados_recientes:
                if ticket.fecha_cierre:
                    tiempo_resolucion = (ticket.fecha_cierre - ticket.fecha_apertura).total_seconds() / 3600
                    tiempos_resolucion.append(tiempo_resolucion)
            
            if tiempos_resolucion:
                tiempo_promedio = sum(tiempos_resolucion) / len(tiempos_resolucion)
        
        return Response({
            'total_tickets': total_tickets,
            'tickets_abiertos': tickets_abiertos,
            'tickets_cerrados_hoy': tickets_cerrados_hoy,
            'tiempo_promedio_resolucion_horas': round(tiempo_promedio, 2),
            'tickets_por_prioridad': list(tickets_por_prioridad),
            'tickets_por_estado': list(tickets_por_estado)
        })

class InteraccionTicketViewSet(viewsets.ModelViewSet):
    queryset = InteraccionTicket.objects.all()
    serializer_class = InteraccionTicketSerializer
    filterset_fields = ['id_ticket', 'tipo_interaccion', 'id_usuario_interactor_temp']
    search_fields = ['contenido']
    ordering_fields = ['fecha_hora_interaccion']
    ordering = ['fecha_hora_interaccion']

    @action(detail=False, methods=['post'])
    def agregar_comentario(self, request):
        """Agrega un comentario a un ticket"""
        ticket_id = request.data.get('ticket_id')
        contenido = request.data.get('contenido')
        
        if not ticket_id or not contenido:
            return Response(
                {'error': 'ticket_id y contenido son requeridos'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            ticket = TicketSoporte.objects.get(pk=ticket_id)
        except TicketSoporte.DoesNotExist:
            return Response(
                {'error': 'Ticket no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        interaccion = InteraccionTicket.objects.create(
            id_ticket=ticket,
            tipo_interaccion='COMENTARIO',
            contenido=contenido,
            id_usuario_interactor_temp=request.user.pk if hasattr(request.user, 'pk') else None
        )
        
        serializer = self.get_serializer(interaccion)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class BaseConocimientoArticuloViewSet(viewsets.ModelViewSet):
    queryset = BaseConocimientoArticulo.objects.all()
    serializer_class = BaseConocimientoArticuloSerializer
    filterset_fields = ['activo', 'visibilidad', 'id_categoria_ticket', 'id_empresa']
    search_fields = ['titulo', 'contenido', 'palabras_clave']
    ordering_fields = ['titulo', 'fecha_publicacion', 'fecha_ultima_revision']
    ordering = ['-fecha_ultima_revision']

    @action(detail=False, methods=['get'])
    def publicos(self, request):
        """Obtiene artículos públicos"""
        empresa_id = request.query_params.get('empresa_id')
        categoria_id = request.query_params.get('categoria_id')
        
        filters = {'activo': True, 'visibilidad': 'PUBLICA'}
        if empresa_id:
            filters['id_empresa'] = empresa_id
        if categoria_id:
            filters['id_categoria_ticket'] = categoria_id
            
        articulos = self.queryset.filter(**filters)
        serializer = self.get_serializer(articulos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def buscar(self, request):
        """Busca artículos por palabras clave"""
        query = request.query_params.get('q')
        empresa_id = request.query_params.get('empresa_id')
        
        if not query:
            return Response(
                {'error': 'Debe especificar una consulta de búsqueda'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        filters = {'activo': True}
        if empresa_id:
            filters['id_empresa'] = empresa_id
        
        # Buscar en título, contenido y palabras clave
        articulos = self.queryset.filter(**filters).filter(
            Q(titulo__icontains=query) |
            Q(contenido__icontains=query) |
            Q(palabras_clave__icontains=query)
        )
        
        serializer = self.get_serializer(articulos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def actualizar_revision(self, request, pk=None):
        """Actualiza la fecha de última revisión del artículo"""
        articulo = self.get_object()
        articulo.fecha_ultima_revision = timezone.now()
        articulo.save()
        
        serializer = self.get_serializer(articulo)
        return Response(serializer.data)

class FeedbackClienteViewSet(viewsets.ModelViewSet):
    queryset = FeedbackCliente.objects.all()
    serializer_class = FeedbackClienteSerializer
    filterset_fields = [
        'tipo_feedback', 'id_empresa', 'id_cliente_temp', 
        'id_ticket_origen', 'calificacion'
    ]
    search_fields = ['comentarios']
    ordering_fields = ['fecha_feedback', 'calificacion']
    ordering = ['-fecha_feedback']

    @action(detail=False, methods=['get'])
    def estadisticas_satisfaccion(self, request):
        """Obtiene estadísticas de satisfacción del cliente"""
        empresa_id = request.query_params.get('empresa_id')
        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        
        filters = {'tipo_feedback': 'ENCUESTA_SATISFACCION', 'calificacion__isnull': False}
        if empresa_id:
            filters['id_empresa'] = empresa_id
        if fecha_desde:
            filters['fecha_feedback__date__gte'] = fecha_desde
        if fecha_hasta:
            filters['fecha_feedback__date__lte'] = fecha_hasta
        
        feedback = self.queryset.filter(**filters)
        
        if not feedback.exists():
            return Response({
                'total_respuestas': 0,
                'calificacion_promedio': 0,
                'distribución_calificaciones': {}
            })
        
        # Calcular estadísticas
        total_respuestas = feedback.count()
        calificacion_promedio = feedback.aggregate(Avg('calificacion'))['calificacion__avg'] or 0
        
        # Distribución de calificaciones
        distribucion = feedback.values('calificacion').annotate(
            count=Count('id_feedback')
        ).order_by('calificacion')
        
        return Response({
            'total_respuestas': total_respuestas,
            'calificacion_promedio': round(calificacion_promedio, 2),
            'distribucion_calificaciones': {
                str(item['calificacion']): item['count'] for item in distribucion
            }
        })

    @action(detail=False, methods=['get'])
    def por_tipo(self, request):
        """Obtiene feedback filtrado por tipo"""
        tipo = request.query_params.get('tipo')
        empresa_id = request.query_params.get('empresa_id')
        
        if not tipo:
            return Response(
                {'error': 'Debe especificar el tipo de feedback'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        filters = {'tipo_feedback': tipo}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        feedback = self.queryset.filter(**filters)
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def quejas_sugerencias(self, request):
        """Obtiene quejas y sugerencias"""
        empresa_id = request.query_params.get('empresa_id')
        
        filters = {'tipo_feedback__in': ['QUEJA', 'SUGERENCIA']}
        if empresa_id:
            filters['id_empresa'] = empresa_id
            
        feedback = self.queryset.filter(**filters)
        serializer = self.get_serializer(feedback, many=True)
        return Response(serializer.data)

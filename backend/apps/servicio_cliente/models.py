import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

class CategoriaTicket(models.Model):
    id_categoria_ticket = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    nombre_categoria = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return str(self.id_empresa)

class TicketSoporte(models.Model):
    id_ticket = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    numero_ticket = models.CharField(max_length=50, unique=True)
    asunto = models.CharField(max_length=255)
    descripcion = models.TextField()
    # id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE, null=True, blank=True)  # Temporalmente comentado
    id_cliente_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    # id_usuario_reporta = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE, null=True, blank=True)  # Temporalmente comentado
    id_usuario_reporta_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    id_categoria_ticket = models.ForeignKey("CategoriaTicket", on_delete=models.CASCADE)
    prioridad = models.CharField(max_length=20, choices=[("BAJA", "Baja"), ("MEDIA", "Media"), ("ALTA", "Alta"), ("URGENTE", "Urgente")])
    estado_ticket = models.CharField(max_length=50, choices=[("ABIERTO", "Abierto"), ("ASIGNADO", "Asignado"), ("EN_PROGRESO", "En Progreso"), ("PENDIENTE_CLIENTE", "Pendiente Cliente"), ("RESUELTO", "Resuelto"), ("CERRADO", "Cerrado"), ("ESCALADO", "Escalado")])
    # id_agente_asignado = models.ForeignKey("rrhh.Empleado", on_delete=models.CASCADE, null=True, blank=True)  # Temporalmente comentado
    id_agente_asignado_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_ultima_actualizacion = models.DateTimeField(auto_now=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    sla_vencimiento = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.asunto)

class InteraccionTicket(models.Model):
    id_interaccion = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_ticket = models.ForeignKey("TicketSoporte", on_delete=models.CASCADE)
    fecha_hora_interaccion = models.DateTimeField(auto_now_add=True)
    tipo_interaccion = models.CharField(max_length=50, choices=[("COMENTARIO", "Comentario"), ("EMAIL", "Email"), ("LLAMADA", "Llamada"), ("CAMBIO_ESTADO", "Cambio Estado"), ("ASIGNACION", "Asignación"), ("ADJUNTO", "Adjunto")])
    # id_usuario_interactor = models.ForeignKey("core.Usuarios", on_delete=models.CASCADE, null=True, blank=True)  # Temporalmente comentado
    id_usuario_interactor_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    contenido = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.id_ticket)

class BaseConocimientoArticulo(models.Model):
    id_articulo = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    titulo = models.CharField(max_length=255)
    contenido = models.TextField()
    id_categoria_ticket = models.ForeignKey("CategoriaTicket", on_delete=models.CASCADE, null=True, blank=True)
    palabras_clave = models.TextField(null=True, blank=True)
    fecha_publicacion = models.DateTimeField(auto_now_add=True)
    fecha_ultima_revision = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)
    visibilidad = models.CharField(max_length=20, choices=[("INTERNA", "Interna"), ("PUBLICA", "Pública")])

    def __str__(self):
        return str(self.titulo)

class FeedbackCliente(models.Model):
    id_feedback = models.UUIDField(primary_key=True, default=uuid.uuid4)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE)
    # id_cliente = models.ForeignKey("crm.Cliente", on_delete=models.CASCADE, null=True, blank=True)  # Temporalmente comentado
    id_cliente_temp = models.UUIDField(null=True, blank=True)  # Campo temporal
    id_ticket_origen = models.ForeignKey("TicketSoporte", on_delete=models.CASCADE, null=True, blank=True)
    fecha_feedback = models.DateTimeField(auto_now_add=True)
    calificacion = models.IntegerField(null=True, blank=True)
    comentarios = models.TextField(null=True, blank=True)
    tipo_feedback = models.CharField(max_length=50, choices=[("ENCUESTA_SATISFACCION", "Encuesta Satisfacción"), ("SUGERENCIA", "Sugerencia"), ("QUEJA", "Queja"), ("OTRO", "Otro")])

    def __str__(self):
        return str(self.id_empresa)

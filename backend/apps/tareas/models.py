"""Modelos del módulo ``apps/tareas`` — Ejecución operativa y proyectos (ADR-015).

Reglas inviolables cumplidas:
- Multi-tenant estricto con ``id_empresa`` en todas las tablas (R-CODE-1) + RLS PostgreSQL.
- PK ``uuid7`` monótono (R-CODE-5).
- Soft delete vía ``OmniBaseModel`` (``activo``) (R-CODE-6).
- Validación cross-tenant explícita en ``clean()`` para todas las FKs entre entidades.
"""

from __future__ import annotations

from datetime import time

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.base_models import OmniBaseModel
from apps.core.uuid import uuid7


def _validar_misma_empresa(id_empresa_id, obj, campo: str, attr_empresa: str = "id_empresa_id") -> None:
    if obj is None or id_empresa_id is None:
        return
    destino_empresa_id = getattr(obj, attr_empresa, None)
    if destino_empresa_id is not None and str(destino_empresa_id) != str(id_empresa_id):
        raise ValidationError({campo: "La entidad referenciada pertenece a otra empresa."})


def _validar_usuario_en_empresa(id_empresa_id, usuario, campo: str) -> None:
    if usuario is None or id_empresa_id is None:
        return
    if getattr(usuario, "es_superusuario_omni", False) or getattr(usuario, "is_superuser", False):
        return
    if not usuario.empresas.filter(pk=id_empresa_id).exists():
        raise ValidationError({campo: "El usuario no pertenece a la empresa indicada."})


class AreaOperativa(OmniBaseModel):
    """Área/equipo de ejecución operativa (conecta opcionalmente con ``core.Departamento``)."""

    id_area = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_areas",
    )
    nombre = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    color = models.CharField(max_length=16, default="#378ADD")
    departamento = models.ForeignKey(
        "core.Departamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="areas_operativas_tareas",
    )
    lider = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="areas_lideradas_tareas",
    )
    palabras_clave = models.JSONField(
        default=list,
        blank=True,
        help_text="Palabras clave para inferir esta área en minutas IA (ej. ['ventas', 'comercial']).",
    )

    class Meta:
        db_table = "tareas_area_operativa"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "slug"],
                condition=Q(activo=True),
                name="tareas_area_empresa_slug_unico",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.departamento, "departamento")
        _validar_usuario_en_empresa(self.id_empresa_id, self.lider, "lider")

    def __str__(self) -> str:
        return self.nombre


class MiembroAreaOperativa(OmniBaseModel):
    """Membresía explícita multi-tenant de un usuario en un ``AreaOperativa``."""

    id_miembro_area = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_miembros_area",
    )
    area = models.ForeignKey(
        AreaOperativa,
        on_delete=models.CASCADE,
        related_name="miembros",
    )
    usuario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.CASCADE,
        related_name="membresias_area_tareas",
    )

    class Meta:
        db_table = "tareas_miembro_area"
        ordering = ["fecha_creacion"]
        constraints = [
            models.UniqueConstraint(
                fields=["area", "usuario"],
                condition=Q(activo=True),
                name="tareas_miembro_area_unico",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.area, "area")
        _validar_usuario_en_empresa(self.id_empresa_id, self.usuario, "usuario")

    def __str__(self) -> str:
        return f"{self.area_id} -> {self.usuario_id}"


class Proyecto(OmniBaseModel):
    """Proyecto o tablero personal/de área con secciones ordenadas."""

    class VistaPredeterminada(models.TextChoices):
        TABLERO = "TABLERO", "Tablero Kanban"
        LISTA = "LISTA", "Lista"
        CALENDARIO = "CALENDARIO", "Calendario"

    id_proyecto = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_proyectos",
    )
    nombre = models.CharField(max_length=160)
    descripcion = models.TextField(blank=True, default="")
    color = models.CharField(max_length=16, default="#1D9E75")
    vista_predeterminada = models.CharField(
        max_length=12,
        choices=VistaPredeterminada.choices,
        default=VistaPredeterminada.TABLERO,
    )
    es_personal = models.BooleanField(
        default=False,
        help_text="True si es el tablero personal automático de un colaborador.",
    )
    archivado = models.BooleanField(default=False)
    area = models.ForeignKey(
        AreaOperativa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proyectos",
    )
    propietario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proyectos_propios_tareas",
    )

    class Meta:
        db_table = "tareas_proyecto"
        ordering = ["es_personal", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "propietario"],
                condition=Q(es_personal=True, activo=True),
                name="tareas_proyecto_personal_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "archivado", "activo"]),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.area, "area")
        _validar_usuario_en_empresa(self.id_empresa_id, self.propietario, "propietario")
        if self.es_personal and self.propietario_id is None:
            raise ValidationError({"propietario": "Un proyecto personal requiere propietario."})

    def __str__(self) -> str:
        return self.nombre


class EstadoTarea(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    EN_EJECUCION = "EN_EJECUCION", "En ejecución"
    EN_REVISION = "EN_REVISION", "En revisión"
    COMPLETADA = "COMPLETADA", "Completada"
    BLOQUEADA = "BLOQUEADA", "Bloqueada"
    CANCELADA = "CANCELADA", "Cancelada"


class PrioridadTarea(models.TextChoices):
    BAJA = "BAJA", "Baja"
    MEDIA = "MEDIA", "Media"
    ALTA = "ALTA", "Alta"
    URGENTE = "URGENTE", "Urgente"


class SeccionProyecto(OmniBaseModel):
    """Columna/sección de un ``Proyecto``; al mover una tarea actualiza su ``estado_destino``."""

    id_seccion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_secciones",
    )
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="secciones",
    )
    nombre = models.CharField(max_length=100)
    estado_destino = models.CharField(
        max_length=16,
        choices=EstadoTarea.choices,
        default=EstadoTarea.PENDIENTE,
    )
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "tareas_seccion_proyecto"
        ordering = ["orden", "fecha_creacion"]
        constraints = [
            models.UniqueConstraint(
                fields=["proyecto", "nombre"],
                condition=Q(activo=True),
                name="tareas_seccion_proyecto_nombre_unico",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.proyecto, "proyecto")

    def __str__(self) -> str:
        return f"{self.nombre} ({self.proyecto_id})"


class PlantillaTareaRecurrente(OmniBaseModel):
    """Definición de tareas recurrentes (intradía, diaria, semanal, quincenal, mensual)."""

    class Frecuencia(models.TextChoices):
        INTRADIA = "INTRADIA", "Intradía"
        DIARIA = "DIARIA", "Diaria"
        SEMANAL = "SEMANAL", "Semanal"
        QUINCENAL = "QUINCENAL", "Quincenal"
        MENSUAL = "MENSUAL", "Mensual"

    id_plantilla_recurrente = models.UUIDField(
        primary_key=True, default=uuid7, editable=False
    )
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_plantillas_recurrentes",
    )
    titulo = models.CharField(max_length=240)
    descripcion = models.TextField(blank=True, default="")
    prioridad = models.CharField(
        max_length=10,
        choices=PrioridadTarea.choices,
        default=PrioridadTarea.MEDIA,
    )
    frecuencia = models.CharField(max_length=12, choices=Frecuencia.choices)
    dias_semana = models.JSONField(
        default=list,
        blank=True,
        help_text="Índices ISO 0..6 (0=lunes .. 6=domingo) para frecuencia semanal.",
    )
    dia_mes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Día del mes (1..31) para frecuencia mensual.",
    )
    horas_dia = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de horas 'HH:MM' para frecuencia intradía.",
    )
    proxima_ejecucion = models.DateField()
    ultima_generacion_en = models.DateTimeField(null=True, blank=True)
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plantillas_recurrentes",
    )
    area = models.ForeignKey(
        AreaOperativa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plantillas_recurrentes",
    )
    asignado_a = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plantillas_tareas_asignadas",
    )
    creado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plantillas_tareas_creadas",
    )

    class Meta:
        db_table = "tareas_plantilla_recurrente"
        ordering = ["proxima_ejecucion", "titulo"]
        constraints = [
            models.CheckConstraint(
                condition=Q(dia_mes__isnull=True) | (Q(dia_mes__gte=1) & Q(dia_mes__lte=31)),
                name="tareas_recurrente_dia_mes_rango",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "activo", "proxima_ejecucion"]),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.proyecto, "proyecto")
        _validar_misma_empresa(self.id_empresa_id, self.area, "area")
        _validar_usuario_en_empresa(self.id_empresa_id, self.asignado_a, "asignado_a")
        _validar_usuario_en_empresa(self.id_empresa_id, self.creado_por, "creado_por")

    def __str__(self) -> str:
        return f"{self.titulo} [{self.frecuencia}]"


class MinutaReunion(OmniBaseModel):
    """Minuta procesada por IA con borrador editable y confirmación atómica a ``Tarea``."""

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador por confirmar"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        DESCARTADA = "DESCARTADA", "Descartada"

    id_minuta = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_minutas",
    )
    titulo = models.CharField(max_length=200)
    fecha_reunion = models.DateField()
    texto_fuente = models.TextField(blank=True, default="")
    documento_adjunto = models.ForeignKey(
        "gestion_documental.Documento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="minutas_tareas",
    )
    borrador_tareas = models.JSONField(
        default=list,
        blank=True,
        help_text="Ítems estructurados propuestos antes de materializar las tareas.",
    )
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    creado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="minutas_tareas_creadas",
    )
    confirmada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tareas_minuta_reunion"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["id_empresa", "estado", "-fecha_creacion"]),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.documento_adjunto, "documento_adjunto")
        _validar_usuario_en_empresa(self.id_empresa_id, self.creado_por, "creado_por")

    def __str__(self) -> str:
        return f"{self.titulo} ({self.estado})"


class Tarea(OmniBaseModel):
    """Unidad central de ejecución operativa, enlazable a cualquier entidad del ERP."""

    class Origen(models.TextChoices):
        WEB = "WEB", "Web"
        BOT = "BOT", "Bot de mensajería"
        MINUTA_IA = "MINUTA_IA", "Minuta con IA"
        RECURRENCIA = "RECURRENCIA", "Plantilla recurrente"
        AGENTE = "AGENTE", "Agente IA"
        ERP_EVENTO = "ERP_EVENTO", "Evento de módulo ERP"

    id_tarea = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_operativas",
    )
    titulo = models.CharField(max_length=240)
    descripcion = models.TextField(blank=True, default="")
    estado = models.CharField(
        max_length=16,
        choices=EstadoTarea.choices,
        default=EstadoTarea.PENDIENTE,
    )
    prioridad = models.CharField(
        max_length=10,
        choices=PrioridadTarea.choices,
        default=PrioridadTarea.MEDIA,
    )
    origen = models.CharField(
        max_length=16,
        choices=Origen.choices,
        default=Origen.WEB,
    )
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )
    seccion = models.ForeignKey(
        SeccionProyecto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )
    area = models.ForeignKey(
        AreaOperativa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )
    tarea_padre = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtareas",
    )
    asignado_a = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_asignadas",
    )
    creado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_creadas",
    )
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    hora_vencimiento = models.TimeField(null=True, blank=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    bloqueada_por_escalacion = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField(max_length=280, blank=True, default="")

    # Vínculo transversal opcional a cualquier documento/objeto de Omni ERP
    entidad_tipo = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Etiqueta 'app.Modelo' del objeto vinculado (ej. ventas.Pedido).",
    )
    entidad_id = models.UUIDField(null=True, blank=True)

    plantilla_recurrente = models.ForeignKey(
        PlantillaTareaRecurrente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_generadas",
    )
    minuta_origen = models.ForeignKey(
        MinutaReunion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_generadas",
    )
    idempotency_key = models.CharField(max_length=120, blank=True, default="")
    orden_tablero = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "tareas_tarea"
        ordering = ["orden_tablero", "fecha_vencimiento", "-fecha_creacion"]
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="tareas_tarea_idem_unica",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "estado", "fecha_vencimiento"]),
            models.Index(fields=["id_empresa", "asignado_a", "estado"]),
            models.Index(fields=["id_empresa", "entidad_tipo", "entidad_id"]),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.proyecto, "proyecto")
        _validar_misma_empresa(self.id_empresa_id, self.seccion, "seccion")
        _validar_misma_empresa(self.id_empresa_id, self.area, "area")
        _validar_misma_empresa(self.id_empresa_id, self.tarea_padre, "tarea_padre")
        _validar_misma_empresa(
            self.id_empresa_id, self.plantilla_recurrente, "plantilla_recurrente"
        )
        _validar_misma_empresa(self.id_empresa_id, self.minuta_origen, "minuta_origen")
        _validar_usuario_en_empresa(self.id_empresa_id, self.asignado_a, "asignado_a")
        _validar_usuario_en_empresa(self.id_empresa_id, self.creado_por, "creado_por")
        if (
            self.seccion is not None
            and self.proyecto_id is not None
            and self.seccion.proyecto_id != self.proyecto_id
        ):
            raise ValidationError(
                {"seccion": "La sección no pertenece al proyecto de la tarea."}
            )
        if self.tarea_padre_id and self.tarea_padre_id == self.id_tarea:
            raise ValidationError(
                {"tarea_padre": "Una tarea no puede ser subtarea de sí misma."}
            )
        if bool(self.entidad_tipo) != (self.entidad_id is not None):
            raise ValidationError(
                {
                    "entidad_tipo": "entidad_tipo y entidad_id deben indicarse juntos o dejarse vacíos."
                }
            )
        if (
            self.fecha_inicio
            and self.fecha_vencimiento
            and self.fecha_vencimiento < self.fecha_inicio
        ):
            raise ValidationError(
                {
                    "fecha_vencimiento": "La fecha de vencimiento no puede ser anterior a la fecha de inicio."
                }
            )

    def __str__(self) -> str:
        return f"{self.titulo} [{self.estado}]"


class DependenciaTarea(OmniBaseModel):
    """Relación de bloqueo entre tareas (``tarea`` depende de ``depende_de``)."""

    id_dependencia = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_dependencias",
    )
    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="dependencias_entrantes",
    )
    depende_de = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="dependencias_salientes",
    )

    class Meta:
        db_table = "tareas_dependencia"
        constraints = [
            models.UniqueConstraint(
                fields=["tarea", "depende_de"],
                condition=Q(activo=True),
                name="tareas_dependencia_unica",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.tarea, "tarea")
        _validar_misma_empresa(self.id_empresa_id, self.depende_de, "depende_de")
        if self.tarea_id and self.tarea_id == self.depende_de_id:
            raise ValidationError(
                {"depende_de": "Una tarea no puede depender de sí misma."}
            )

    def __str__(self) -> str:
        return f"{self.tarea_id} <- {self.depende_de_id}"


class ComentarioTarea(OmniBaseModel):
    """Bitácora conversacional y de eventos sobre una ``Tarea``."""

    id_comentario = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_comentarios",
    )
    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="comentarios",
    )
    autor = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comentarios_tareas",
    )
    autor_nombre = models.CharField(max_length=150, blank=True, default="")
    cuerpo = models.TextField()
    es_sistema = models.BooleanField(default=False)

    class Meta:
        db_table = "tareas_comentario"
        ordering = ["fecha_creacion"]
        indexes = [
            models.Index(fields=["tarea", "fecha_creacion"]),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.tarea, "tarea")
        _validar_usuario_en_empresa(self.id_empresa_id, self.autor, "autor")

    def __str__(self) -> str:
        return f"Comentario {self.id_comentario} en {self.tarea_id}"


class ConfiguracionSeguimientoTareas(OmniBaseModel):
    """Parámetros de horarios de recordatorio, reporte diario y escalación por empresa."""

    id_config_seguimiento = models.UUIDField(
        primary_key=True, default=uuid7, editable=False
    )
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_configuraciones_seguimiento",
    )
    zona_horaria = models.CharField(max_length=50, default="America/Caracas")
    hora_recordatorio_manana = models.TimeField(default=time(9, 0))
    hora_recordatorio_tarde = models.TimeField(default=time(15, 0))
    hora_reporte_gerencial = models.TimeField(default=time(18, 0))
    horas_bloqueo_vencida = models.PositiveSmallIntegerField(default=72)
    gerente = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="empresas_gerenciadas_tareas",
    )

    class Meta:
        db_table = "tareas_configuracion_seguimiento"
        constraints = [
            models.UniqueConstraint(
                fields=["id_empresa"],
                condition=Q(activo=True),
                name="tareas_config_seguimiento_empresa_unica",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_usuario_en_empresa(self.id_empresa_id, self.gerente, "gerente")

    def __str__(self) -> str:
        return f"Seguimiento {self.id_empresa_id}"


class RegistroAlertaTarea(OmniBaseModel):
    """Bitácora idempotente de recordatorios y escalaciones emitidos por ``Tarea``."""

    id_alerta_tarea = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="tareas_alertas_emitidas",
    )
    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="alertas_emitidas",
    )
    clave_alerta = models.CharField(max_length=80)
    destinatario = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alertas_tareas_recibidas",
    )
    canal = models.CharField(max_length=20, default="IN_APP")
    detalle = models.CharField(max_length=280, blank=True, default="")

    class Meta:
        db_table = "tareas_registro_alerta"
        ordering = ["-fecha_creacion"]
        constraints = [
            models.UniqueConstraint(
                fields=["tarea", "clave_alerta"],
                name="tareas_alerta_clave_unica",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "-fecha_creacion"]),
        ]

    def clean(self) -> None:
        super().clean()
        _validar_misma_empresa(self.id_empresa_id, self.tarea, "tarea")
        _validar_usuario_en_empresa(self.id_empresa_id, self.destinatario, "destinatario")

    def __str__(self) -> str:
        return f"{self.tarea_id}:{self.clave_alerta}"

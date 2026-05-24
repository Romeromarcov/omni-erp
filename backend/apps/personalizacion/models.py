import uuid
from apps.core.uuid import uuid7

from django.db import models


class PersonalizacionConfig(models.Model):
    """
    Almacena una versión del DSL de personalización para una empresa.

    Cada empresa tiene un historial de configuraciones. Solo una puede estar
    activa (activo=True) a la vez. Las anteriores se conservan para rollback.
    """

    id_config = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, db_index=True)
    version = models.PositiveIntegerField(default=1)
    descripcion = models.CharField(max_length=200, blank=True)
    config_yaml = models.TextField()
    config_dict = models.JSONField()
    activo = models.BooleanField(default=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_aplicacion = models.DateTimeField(null=True, blank=True)
    resultado_aplicacion = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [["id_empresa", "version"]]
        ordering = ["-version"]

    def __str__(self):
        return f"Config v{self.version} ({self.id_empresa})"


class EntidadInstancia(models.Model):
    """
    Instancia de una entidad personalizada (EAV genérico) — CTF-002.

    Almacena registros para entidades definidas en el DSL de personalización.
    Los campos se guardan en 'datos' como JSON libre.

    Ejemplo:
        EntidadInstancia.objects.create(
            id_empresa=empresa,
            nombre_entidad="Equipo",
            datos={"nombre": "Laptop Pro", "numero_serie": "SN-123"},
        )
    """

    id_instancia = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="entidades_instancias",
    )
    nombre_entidad = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Nombre de la entidad DSL (ej: 'Equipo', 'Contrato')",
    )
    datos = models.JSONField(
        default=dict,
        help_text="Campos de la instancia según la definición DSL de la entidad",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "personalizacion_entidad_instancia"
        verbose_name = "Instancia de Entidad"
        verbose_name_plural = "Instancias de Entidades"
        indexes = [
            models.Index(fields=["id_empresa", "nombre_entidad"]),
        ]

    def __str__(self):
        return f"{self.nombre_entidad} #{self.id_instancia.hex[:8]} ({self.id_empresa})"


class EstadoPersonalizado(models.Model):
    """
    Estado personalizado de workflow definido via DSL — CTF-002.

    Permite agregar estados adicionales a modelos existentes sin modificar
    el choices del modelo. Los viewsets pueden consultarlo para validar
    transiciones de estado.
    """

    id_estado = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="estados_personalizados",
    )
    modelo = models.CharField(
        max_length=100,
        help_text="Nombre del modelo Django al que aplica (ej: 'Pedido', 'Gasto')",
    )
    nombre = models.CharField(
        max_length=50,
        help_text="Clave del estado (ej: 'EN_REVISION')",
    )
    etiqueta = models.CharField(
        max_length=100,
        help_text="Texto para mostrar al usuario (ej: 'En Revisión')",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "personalizacion_estado_personalizado"
        verbose_name = "Estado Personalizado"
        verbose_name_plural = "Estados Personalizados"
        unique_together = [["id_empresa", "modelo", "nombre"]]
        indexes = [
            models.Index(fields=["id_empresa", "modelo"]),
        ]

    def __str__(self):
        return f"{self.modelo}.{self.nombre} ({self.id_empresa})"


class VistaPersonalizada(models.Model):
    """
    Preferencias de columnas y filtros para un listado — CTF-002.

    Almacena qué columnas son visibles, en qué orden y con qué filtros
    para un usuario/empresa en un listado determinado.
    """

    id_vista = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="vistas_personalizadas",
    )
    entidad = models.CharField(
        max_length=100,
        help_text="Nombre del listado/entidad (ej: 'Cliente', 'Pedido')",
    )
    columnas = models.JSONField(
        default=list,
        help_text="Lista de nombres de columna a mostrar, en orden",
    )
    filtros = models.JSONField(
        default=dict,
        help_text="Filtros por defecto para esta vista",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "personalizacion_vista_personalizada"
        verbose_name = "Vista Personalizada"
        verbose_name_plural = "Vistas Personalizadas"
        unique_together = [["id_empresa", "entidad"]]
        indexes = [
            models.Index(fields=["id_empresa", "entidad"]),
        ]

    def __str__(self):
        return f"Vista:{self.entidad} ({self.id_empresa})"

import uuid

from django.db import models


class PersonalizacionConfig(models.Model):
    """
    Almacena una versión del DSL de personalización para una empresa.

    Cada empresa tiene un historial de configuraciones. Solo una puede estar
    activa (activo=True) a la vez. Las anteriores se conservan para rollback.
    """

    id_config = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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

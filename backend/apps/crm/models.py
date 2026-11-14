import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.base_models import IntegrationFieldsMixin, OmniBaseModel
from apps.core.uuid import uuid7
from apps.core.validators import validar_misma_empresa


def validar_rif(value):
    if not re.match(r"^[VJEGBP]-[0-9]+$", value):
        raise ValidationError("RIF debe tener formato Letra-Mayúscula (V/J/E/G/B/P) seguida de guion y números.")


def validar_telefono(value):
    # Acepta móviles y fijos venezolanos, y formatos internacionales con +
    cleaned = re.sub(r"[\s\-\(\)]", "", value)
    if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
        raise ValidationError("Teléfono inválido. Ingrese entre 7 y 15 dígitos, con prefijo + opcional.")


class Cliente(OmniBaseModel, IntegrationFieldsMixin):
    """
    Cliente del negocio. Hereda timestamps, soft-delete e integración externa.
    RIF único por empresa (no globalmente) para soportar multi-tenant.
    """

    id_cliente = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="clientes")
    razon_social = models.CharField(max_length=255)
    nombre_comercial = models.CharField(max_length=255, null=True, blank=True)
    rif = models.CharField(max_length=20, validators=[validar_rif])
    direccion = models.TextField(null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True, validators=[validar_telefono])
    email = models.EmailField(null=True, blank=True)
    tipo_cliente = models.CharField(
        max_length=10,
        choices=[("CONTADO", "Contado"), ("CREDITO", "Crédito")],
        default="CONTADO",
    )
    limite_credito = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Límite de crédito aprobado. 0 = sin límite definido (requiere tipo_cliente=CREDITO).",
    )
    dias_credito = models.PositiveSmallIntegerField(
        default=0,
        help_text="Días de plazo de crédito.",
    )

    # Enlace al Contacto unificado (strangler fig — nullable durante transición)
    contacto = models.OneToOneField(
        "core.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cliente",
    )

    class Meta:
        ordering = ["razon_social"]
        unique_together = [["id_empresa", "rif"]]

    def __str__(self):
        return self.razon_social


class ContactoCliente(OmniBaseModel):
    id_contacto = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="contactos_cliente")
    id_cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="contactos")
    nombre_contacto = models.CharField(max_length=100)
    apellido_contacto = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    telefono_directo = models.CharField(max_length=50, null=True, blank=True)
    telefono_movil = models.CharField(max_length=50, null=True, blank=True)
    email_contacto = models.EmailField()
    fecha_nacimiento = models.DateField(null=True, blank=True)
    es_contacto_principal = models.BooleanField(default=False)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "crm_contacto_cliente"
        verbose_name = "Contacto de Cliente"
        verbose_name_plural = "Contactos de Cliente"

    def __str__(self):
        return f"{self.nombre_contacto} {self.apellido_contacto} - {self.id_cliente.razon_social}"


class DireccionCliente(OmniBaseModel):
    TIPOS_DIRECCION = [
        ("FISCAL", "Fiscal"),
        ("COMERCIAL", "Comercial"),
        ("ENTREGA", "Entrega"),
        ("FACTURACION", "Facturación"),
        ("OTRA", "Otra"),
    ]

    id_direccion = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="direcciones_cliente")
    id_cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="direcciones")
    tipo_direccion = models.CharField(max_length=20, choices=TIPOS_DIRECCION)
    direccion_completa = models.TextField()
    ciudad = models.CharField(max_length=100)
    estado_provincia = models.CharField(max_length=100)
    codigo_postal = models.CharField(max_length=20, null=True, blank=True)
    pais = models.CharField(max_length=100, default="Venezuela")
    telefono = models.CharField(max_length=50, null=True, blank=True)
    persona_contacto = models.CharField(max_length=100, null=True, blank=True)
    es_direccion_principal = models.BooleanField(default=False)
    observaciones = models.TextField(null=True, blank=True)

    # Geolocalización (capturada p. ej. desde el bot de Telegram) para ubicar al cliente en mapa/rutas.
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_precision_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    gps_capturado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crm_direccion_cliente"
        verbose_name = "Dirección de Cliente"
        verbose_name_plural = "Direcciones de Cliente"

    def __str__(self):
        return f"{self.tipo_direccion} - {self.id_cliente.razon_social} ({self.ciudad})"


# ── CRM ligero (Omni Connect, S1): pipeline, etapas y leads ───────────────────


class Pipeline(OmniBaseModel):
    """Embudo de ventas del tenant. Se crea uno predeterminado por empresa (S4)."""

    id_pipeline = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="crm_pipelines")
    nombre = models.CharField(max_length=100)
    es_predeterminado = models.BooleanField(default=False)

    class Meta:
        db_table = "crm_pipeline"
        verbose_name = "Pipeline"
        verbose_name_plural = "Pipelines"
        ordering = ["nombre"]
        constraints = [
            # Unicidad solo entre pipelines activos: el nombre de uno desactivado se puede reutilizar.
            models.UniqueConstraint(
                fields=["id_empresa", "nombre"],
                condition=models.Q(activo=True),
                name="crm_pipeline_nombre_unico",
            ),
            # A lo sumo un pipeline predeterminado (activo) por empresa.
            models.UniqueConstraint(
                fields=["id_empresa"],
                condition=models.Q(es_predeterminado=True, activo=True),
                name="crm_pipeline_un_predeterminado",
            ),
        ]

    def __str__(self):
        return self.nombre


class Etapa(OmniBaseModel):
    """Etapa configurable de un pipeline (Nuevo, Contactado, Calificado, Ganado, Perdido)."""

    class Tipo(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        GANADA = "GANADA", "Ganada"
        PERDIDA = "PERDIDA", "Perdida"

    id_etapa = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    # Redundante con pipeline.id_empresa: necesario para que RLS filtre la tabla
    # directamente. clean() garantiza que ambas coincidan.
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="crm_etapas")
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="etapas")
    nombre = models.CharField(max_length=100)
    orden = models.PositiveSmallIntegerField(default=0)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ABIERTA)

    class Meta:
        db_table = "crm_etapa"
        verbose_name = "Etapa"
        verbose_name_plural = "Etapas"
        # ``orden`` no es único: reordenar (drag-and-drop del kanban) intercambia posiciones
        # y una restricción no diferible lo rechazaría a mitad de la actualización.
        ordering = ["pipeline", "orden", "nombre"]
        constraints = [
            # Unicidad solo entre etapas activas: el nombre de una desactivada se puede reutilizar.
            models.UniqueConstraint(
                fields=["pipeline", "nombre"],
                condition=models.Q(activo=True),
                name="crm_etapa_nombre_unico",
            ),
        ]
        indexes = [models.Index(fields=["id_empresa", "pipeline"])]

    def __str__(self):
        return f"{self.pipeline.nombre} · {self.nombre}"

    def clean(self):
        super().clean()
        validar_misma_empresa(self, pipeline=self.pipeline)


class Lead(OmniBaseModel):
    """Contacto capturado (perfil NFC, QR o carga manual) antes de ser cliente.

    Al ganarse se convierte en ``Cliente`` (S6). Los datos personales de un
    tercero se guardan solo con consentimiento explícito, fechado y con el texto
    aceptado; el derecho de borrado se atiende en S7 (outbox).
    """

    class Fuente(models.TextChoices):
        NFC = "NFC", "Tarjeta NFC"
        QR = "QR", "Código QR"
        ENLACE = "ENLACE", "Enlace de perfil"
        MANUAL = "MANUAL", "Carga manual"
        IMPORTACION = "IMPORTACION", "Importación"

    id_lead = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    id_empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="crm_leads")
    nombre = models.CharField(max_length=150)
    apellido = models.CharField(max_length=150, blank=True, default="")
    empresa_nombre = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    telefono = models.CharField(max_length=50, blank=True, default="")
    # Formas normalizadas (se llenan en S5) para deduplicar por teléfono/correo.
    email_normalizado = models.CharField(max_length=254, blank=True, default="")
    telefono_normalizado = models.CharField(max_length=20, blank=True, default="")
    mensaje = models.TextField(blank=True, default="")

    fuente = models.CharField(max_length=12, choices=Fuente.choices, default=Fuente.MANUAL)
    tarjeta = models.ForeignKey(
        "connect.Tarjeta", on_delete=models.SET_NULL, null=True, blank=True, related_name="leads"
    )
    perfil = models.ForeignKey(
        "connect.Perfil", on_delete=models.SET_NULL, null=True, blank=True, related_name="leads"
    )

    pipeline = models.ForeignKey(Pipeline, on_delete=models.PROTECT, related_name="leads")
    etapa = models.ForeignKey(Etapa, on_delete=models.PROTECT, related_name="leads")
    # Dueño del lead: el dueño de la tarjeta/perfil, o quien lo carga a mano.
    propietario = models.ForeignKey("core.Usuarios", on_delete=models.PROTECT, related_name="crm_leads")
    # Persona resuelta en el contacto unificado (deduplicación, S5); nula hasta entonces.
    contacto = models.ForeignKey(
        "core.Contacto", on_delete=models.SET_NULL, null=True, blank=True, related_name="leads"
    )

    consentimiento_aceptado = models.BooleanField(default=False)
    consentimiento_fecha = models.DateTimeField(null=True, blank=True)
    consentimiento_texto = models.TextField(blank=True, default="")

    class Meta:
        db_table = "crm_lead"
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ["-fecha_creacion"]
        constraints = [
            # Consentimiento aceptado => fecha y texto aceptado guardados.
            models.CheckConstraint(
                condition=models.Q(consentimiento_aceptado=False)
                | (models.Q(consentimiento_fecha__isnull=False) & ~models.Q(consentimiento_texto="")),
                name="crm_lead_consentimiento_completo",
            ),
            # Todo lead capturado por la vía pública (NFC/QR/enlace) exige consentimiento.
            models.CheckConstraint(
                condition=models.Q(fuente__in=["MANUAL", "IMPORTACION"]) | models.Q(consentimiento_aceptado=True),
                name="crm_lead_publico_requiere_consentimiento",
            ),
        ]
        indexes = [
            models.Index(fields=["id_empresa", "etapa"]),
            models.Index(fields=["id_empresa", "propietario"]),
            models.Index(fields=["id_empresa", "email_normalizado"]),
            models.Index(fields=["id_empresa", "telefono_normalizado"]),
            models.Index(fields=["id_empresa", "fecha_creacion"]),
        ]

    def __str__(self):
        return f"{self.nombre} {self.apellido}".strip()

    def clean(self):
        super().clean()
        validar_misma_empresa(
            self,
            pipeline=self.pipeline,
            etapa=self.etapa,
            tarjeta=self.tarjeta,
            perfil=self.perfil,
            contacto=self.contacto,
        )
        if self.etapa_id and self.pipeline_id and self.etapa.pipeline_id != self.pipeline_id:
            raise ValidationError({"etapa": "La etapa no pertenece al pipeline del lead."})
        if self.tarjeta_id and self.perfil_id and self.tarjeta.perfil_id != self.perfil_id:
            raise ValidationError({"tarjeta": "La tarjeta no está asignada al perfil del lead."})
        if self.propietario_id and not self.propietario.empresas.filter(pk=self.id_empresa_id).exists():
            raise ValidationError({"propietario": "El propietario no pertenece a esta empresa."})

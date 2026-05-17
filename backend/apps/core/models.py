# apps/core/models.py
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .base_models import IntegrationFieldsMixin, OmniBaseModel


class Empresa(OmniBaseModel, IntegrationFieldsMixin):
    """
    Empresa cliente del ERP. Entidad raíz del multi-tenant.
    fecha_creacion proviene de OmniBaseModel (antes: fecha_registro).
    """

    empresa_matriz = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="subsidiarias",
        on_delete=models.SET_NULL,
        verbose_name="Empresa Matriz",
    )
    id_empresa = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre_legal = models.CharField(max_length=255, verbose_name="Nombre Legal")
    nombre_comercial = models.CharField(max_length=255, null=True, blank=True, verbose_name="Nombre Comercial")
    identificador_fiscal = models.CharField(max_length=20, blank=True, null=True)
    direccion_fiscal = models.TextField(null=True, blank=True, verbose_name="Dirección Fiscal")
    telefono = models.CharField(max_length=20, null=True, blank=True, verbose_name="Teléfono")
    email_contacto = models.EmailField(null=True, blank=True, verbose_name="Email de Contacto")
    web_url = models.URLField(null=True, blank=True, verbose_name="URL Web")
    logo_url = models.URLField(null=True, blank=True, verbose_name="URL del Logo")
    id_moneda_base = models.ForeignKey(
        "finanzas.Moneda",
        on_delete=models.SET_NULL,
        db_column="id_moneda_base",
        blank=True,
        null=True,
        related_name="empresas_base",
        verbose_name="Moneda Base",
    )
    id_moneda_pais = models.ForeignKey(
        "finanzas.Moneda",
        on_delete=models.SET_NULL,
        db_column="id_moneda_pais",
        blank=True,
        null=True,
        related_name="empresas_moneda_pais",
        verbose_name="Moneda del País",
    )
    pais_codigo_iso = models.CharField(max_length=3, null=True, blank=True, verbose_name="Código ISO del País")
    pais_nombre = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nombre del País")
    tipo_operacion = models.CharField(max_length=50, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    contabilidad_auto_aprobar = models.BooleanField(
        default=False,
        help_text="Si True, los asientos contables generados automáticamente se aprueban de inmediato.",
    )

    class Meta:
        db_table = "empresas"
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["nombre_legal"]

    def __str__(self):
        return self.nombre_comercial if self.nombre_comercial else self.nombre_legal


class Sucursal(OmniBaseModel, IntegrationFieldsMixin):
    sucursal_matriz = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="subsucursales",
        on_delete=models.SET_NULL,
        verbose_name="Sucursal Matriz",
    )
    id_sucursal = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, db_column="id_empresa", related_name="sucursales", verbose_name="Empresa"
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre de Sucursal")
    codigo_sucursal = models.CharField(max_length=10, unique=True, verbose_name="Código de Sucursal")
    direccion = models.TextField(null=True, blank=True, verbose_name="Dirección")
    telefono = models.CharField(max_length=20, null=True, blank=True, verbose_name="Teléfono")
    email_contacto = models.EmailField(null=True, blank=True, verbose_name="Email de Contacto")
    ubicacion_gps_json = models.JSONField(null=True, blank=True, verbose_name="Ubicación GPS")

    class Meta:
        db_table = "sucursales"
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"
        unique_together = (("id_empresa", "codigo_sucursal"),)
        ordering = ["id_empresa", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.id_empresa.nombre_comercial if self.id_empresa.nombre_comercial else self.id_empresa.nombre_legal})"


class Departamento(OmniBaseModel, IntegrationFieldsMixin):
    departamento_general = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="subdepartamentos",
        on_delete=models.SET_NULL,
        verbose_name="Dirección General",
    )
    id_departamento = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, db_column="id_empresa", related_name="departamentos", verbose_name="Empresa"
    )
    nombre_departamento = models.CharField(max_length=100, verbose_name="Nombre de Departamento")
    descripcion = models.TextField(null=True, blank=True, verbose_name="Descripción")

    class Meta:
        db_table = "departamentos"
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        unique_together = (("id_empresa", "nombre_departamento"),)
        ordering = ["id_empresa", "nombre_departamento"]

    def __str__(self):
        return f"{self.nombre_departamento} ({self.id_empresa.nombre_comercial if self.id_empresa.nombre_comercial else self.id_empresa.nombre_legal})"


# 4. Modelo de Usuario Personalizado (Actualizado)
# Extiende AbstractUser para incluir campos adicionales si son necesarios
# y para usar el sistema de autenticación de Django.
class Usuarios(AbstractUser):
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    documento_json = models.JSONField(null=True, blank=True)
    # Hereda campos como username, email, first_name, last_name, is_staff, is_active, date_joined, etc.
    # Sobreescribimos el campo id para usar UUIDField como PK
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )  # Usamos 'id' como PK para AbstractUser
    empresas = models.ManyToManyField(Empresa, related_name="usuarios")
    # Eliminamos el campo 'id_rol' directo aquí, ya que se maneja con la tabla intermedia UsuarioRoles
    sucursales = models.ManyToManyField(Sucursal, related_name="usuarios")
    es_superusuario_omni = models.BooleanField(
        default=False, verbose_name="Es Superusuario Omni ERP"
    )  # Para superadministradores de Omni ERP, no de la empresa cliente.
    id_sucursal_predeterminada = models.ForeignKey(
        "Sucursal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios_predeterminados",
        verbose_name="Sucursal predeterminada",
    )
    fecha_ultimo_login = models.DateTimeField(null=True, blank=True, verbose_name="Fecha Último Login")
    # NOTE: token_sesion removed — JWT tokens must not be stored in the DB; use the blacklist table
    # id_empleado = models.ForeignKey(Empleado, on_delete=models.SET_NULL, db_column='id_empleado', blank=True, null=True, related_name='usuario_erp', verbose_name="Empleado Asociado")
    # Nota: La FK a Empleado se añadirá cuando el módulo de rrhh esté implementado.

    def get_cajas_virtuales_disponibles(self, empresa=None):
        """
        Retorna las cajas virtuales disponibles para este usuario basado en:
        1. Cajas físicas asignadas al usuario
        2. Cajas virtuales asociadas a esas cajas físicas
        3. Permisos según el tipo de caja (registradora vs matriz/gerencia)

        Args:
            empresa: Filtrar por empresa específica (opcional)

        Returns:
            QuerySet de cajas virtuales disponibles
        """
        from apps.finanzas.models import Caja, CajaFisicaUsuario

        # Obtener cajas físicas asignadas al usuario
        cajas_fisicas_usuario = CajaFisicaUsuario.objects.filter(usuario=self).select_related("caja_fisica")

        if empresa:
            cajas_fisicas_usuario = cajas_fisicas_usuario.filter(caja_fisica__empresa=empresa)

        # Obtener IDs de cajas físicas
        cajas_fisicas_ids = cajas_fisicas_usuario.values_list("caja_fisica", flat=True)

        # Obtener cajas virtuales asociadas a estas cajas físicas
        cajas_virtuales = Caja.objects.filter(caja_fisica__in=cajas_fisicas_ids).select_related(
            "caja_fisica", "moneda"
        )

        # Aplicar filtros de permisos según tipo de caja
        cajas_permitidas = []

        for caja_virtual in cajas_virtuales:
            caja_fisica = caja_virtual.caja_fisica
            if caja_fisica:
                # Verificar permisos del usuario para esta caja física
                asignacion = cajas_fisicas_usuario.filter(caja_fisica=caja_fisica).first()
                if asignacion:
                    tipo_caja = caja_virtual.tipo_caja

                    # Cajas registradoras: cualquier usuario puede acceder
                    if tipo_caja == "REGISTRADORA":
                        cajas_permitidas.append(caja_virtual.id_caja)

                    # Cajas de gerencia y matriz: solo usuarios con permisos específicos
                    elif tipo_caja in ["GERENCIA", "MATRIZ"]:
                        # Aquí se pueden agregar validaciones adicionales de permisos
                        # Por ahora, permitimos acceso si el usuario está asignado a la caja física
                        cajas_permitidas.append(caja_virtual.id_caja)

                    # Otros tipos
                    else:
                        cajas_permitidas.append(caja_virtual.id_caja)

        return Caja.objects.filter(id_caja__in=cajas_permitidas).select_related("caja_fisica", "moneda")

    class Meta:
        db_table = "usuarios"  # Nombre de la tabla en la base de datos
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        # Añadimos unique_together para username e id_empresa si el username debe ser único por empresa
        # Si el username es globalmente único (como en AbstractUser), no es necesario.
        # Si quieres que el username sea único por empresa, necesitas quitar unique=True de username en AbstractUser
        # y luego añadirlo aquí. Por simplicidad, mantenemos el comportamiento de AbstractUser.
        ordering = ["username"]

    def __str__(self):
        return self.username  # O self.email si lo usas como identificador principal


# 5. Modelo de Roles (Actualizado)
# Define los diferentes roles que los usuarios pueden tener en el sistema (ej. Administrador, Vendedor, Almacenista).
class Roles(OmniBaseModel, IntegrationFieldsMixin):
    """
    Roles de usuario en el sistema.
    Hereda: fecha_creacion, fecha_actualizacion, activo (OmniBaseModel)
            referencia_externa, documento_json (IntegrationFieldsMixin)
    """

    id_rol = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        db_column="id_empresa",
        blank=True,
        null=True,
        related_name="roles_empresa",
        verbose_name="Empresa (Opcional)",
    )  # Puede ser un rol global o específico de la empresa.
    nombre_rol = models.CharField(max_length=100, verbose_name="Nombre de Rol")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")  # Cambiado a TextField

    class Meta:
        db_table = "roles"
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        unique_together = (
            ("id_empresa", "nombre_rol"),
        )  # Nombre de rol único por empresa (o global si id_empresa es null)
        ordering = ["nombre_rol"]

    def __str__(self):
        return self.nombre_rol


# 6. Modelo de Permisos (Actualizado)
# Define las acciones o recursos específicos a los que se puede acceder (ej. 'ventas.crear_factura', 'inventario.ver_stock').
class Permisos(OmniBaseModel, IntegrationFieldsMixin):
    """
    Permisos granulares del sistema.
    Hereda: fecha_creacion, fecha_actualizacion, activo (OmniBaseModel)
            referencia_externa, documento_json (IntegrationFieldsMixin)
    """

    id_permiso = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, db_column='id_empresa', blank=True, null=True, related_name='permisos_empresa', verbose_name="Empresa (Opcional)") # Permisos pueden ser globales o por empresa
    # El esquema original no tenía id_empresa para Permisos, lo mantendremos así por ahora.
    codigo_permiso = models.CharField(
        max_length=100, unique=True, verbose_name="Código de Permiso"
    )  # Ej: ventas.crear_pedido, finanzas.ver_balance.
    nombre_permiso = models.CharField(max_length=255, verbose_name="Nombre de Permiso")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")  # Cambiado a TextField
    modulo = models.CharField(max_length=50, verbose_name="Módulo Asociado")  # Ej: ventas, finanzas.

    class Meta:
        db_table = "permisos"
        verbose_name = "Permiso"
        verbose_name_plural = "Permisos"
        ordering = ["modulo", "nombre_permiso"]

    def __str__(self):
        return self.nombre_permiso


# 7. Modelo de Relación Rol-Permiso (Muchos a Muchos) (Actualizado)
# Asocia permisos específicos a roles.
class RolPermisos(models.Model):
    id_rol_permiso = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_rol = models.ForeignKey(
        Roles, on_delete=models.CASCADE, db_column="id_rol", related_name="permisos_asignados", verbose_name="Rol"
    )
    id_permiso = models.ForeignKey(
        Permisos,
        on_delete=models.CASCADE,
        db_column="id_permiso",
        related_name="roles_asignados",
        verbose_name="Permiso",
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Asignación")

    class Meta:
        db_table = "rol_permisos"
        unique_together = (("id_rol", "id_permiso"),)  # Un rol no puede tener el mismo permiso dos veces
        verbose_name = "Permiso de Rol"
        verbose_name_plural = "Permisos de Roles"
        ordering = ["id_rol__nombre_rol", "id_permiso__nombre_permiso"]

    def __str__(self):
        return f"{self.id_rol.nombre_rol} - {self.id_permiso.nombre_permiso}"


# 8. Modelo de Relación Usuario-Rol (Muchos a Muchos) (Actualizado)
# Asocia usuarios a roles. Un usuario puede tener múltiples roles.
class UsuarioRoles(models.Model):
    id_usuario_rol = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.CASCADE,
        db_column="id_usuario",
        related_name="roles_asignados",
        verbose_name="Usuario",
    )
    id_rol = models.ForeignKey(
        Roles, on_delete=models.CASCADE, db_column="id_rol", related_name="usuarios_asignados", verbose_name="Rol"
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Asignación")

    class Meta:
        db_table = "usuario_roles"
        unique_together = (("id_usuario", "id_rol"),)  # Un usuario no puede tener el mismo rol dos veces
        verbose_name = "Rol de Usuario"
        verbose_name_plural = "Roles de Usuarios"
        ordering = ["id_usuario__username", "id_rol__nombre_rol"]

    def __str__(self):
        return f"{self.id_usuario.username} - {self.id_rol.nombre_rol}"


# 9. Modelo de Registro de Auditoría (Actualizado)
# Registra acciones importantes realizadas en el sistema para trazabilidad.
class RegistroAuditoria(models.Model):
    id_log_auditoria = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # PK, UUIDField
    id_empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        db_column="id_empresa",
        related_name="registros_auditoria_empresa",
        verbose_name="Empresa",
    )
    id_usuario = models.ForeignKey(
        Usuarios,
        on_delete=models.SET_NULL,
        db_column="id_usuario",
        blank=True,
        null=True,
        related_name="registros_auditoria_usuario",
        verbose_name="Usuario",
    )
    tipo_evento = models.CharField(
        max_length=50,
        choices=[
            ("LOGIN", "Inicio de Sesión"),
            ("LOGOUT", "Cierre de Sesión"),
            ("CREAR", "Creación"),
            ("ACTUALIZAR", "Actualización"),
            ("ELIMINAR", "Eliminación"),
            ("ACCEDER", "Acceso a Datos"),
            ("ERROR", "Error del Sistema"),
            ("CAMBIO_ESTADO", "Cambio de Estado"),
            ("APROBACION", "Aprobación"),
            ("RECHAZO", "Rechazo"),
            ("PAGO_CONFIRMADO", "Pago Confirmado"),
            ("ENTREGA_REGISTRADA", "Entrega Registrada"),
            ("INCIDENCIA_CREADA", "Incidencia Creada"),
            # Añadir más tipos de eventos según sea necesario
        ],
        verbose_name="Tipo de Evento",
    )
    modulo_afectado = models.CharField(max_length=50, verbose_name="Módulo Afectado")  # Ej: 'ventas', 'finanzas'.
    nombre_modelo_afectado = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="Modelo Afectado"
    )  # Ej: 'Factura', 'Producto'.
    id_registro_afectado = models.CharField(
        max_length=255, null=True, blank=True, verbose_name="ID Registro Afectado"
    )  # ID del objeto afectado (puede ser UUID, int, etc.)
    descripcion_accion = models.TextField(
        null=True, blank=True, verbose_name="Descripción de la Acción"
    )  # Detalles legibles de la acción.
    cambios_json = models.JSONField(
        blank=True, null=True, verbose_name="Cambios (JSON)"
    )  # Contiene los datos antiguos y nuevos para acciones de actualización.
    fecha_hora_accion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora de la Acción")
    direccion_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="Dirección IP")
    navegador_info = models.TextField(null=True, blank=True, verbose_name="Información del Navegador")
    resultado_evento = models.CharField(
        max_length=20, choices=[("EXITO", "Éxito"), ("FALLO", "Fallo")], verbose_name="Resultado del Evento"
    )
    mensaje_error = models.TextField(null=True, blank=True, verbose_name="Mensaje de Error")
    # id_documento_asociado = models.ForeignKey('gestion_documental.Documento', on_delete=models.SET_NULL, db_column='id_documento_asociado', blank=True, null=True, related_name='registros_auditoria_documento', verbose_name="Documento Asociado")
    # Nota: La FK a Documento se añadirá cuando el módulo de gestion_documental esté implementado.

    class Meta:
        db_table = "registro_auditoria"
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"
        ordering = ["-fecha_hora_accion"]  # Ordenar por fecha descendente

    def __str__(self):
        return f"[{self.fecha_hora_accion.strftime('%Y-%m-%d %H:%M')}] {self.id_usuario.username if self.id_usuario else 'N/A'} - {self.tipo_evento} en {self.modulo_afectado}.{self.nombre_modelo_afectado} (ID: {self.id_registro_afectado})"


# 10. Modelo de Dispositivo (Para detección automática y asociación con cajas físicas)
class Dispositivo(models.Model):
    """
    Modelo para registrar dispositivos que acceden al sistema.
    Permite detectar automáticamente dispositivos y asociarlos con cajas físicas.
    """

    id_dispositivo = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identificación única del dispositivo
    fingerprint = models.CharField(
        max_length=255, unique=True, help_text="Hash único generado por el frontend (FingerprintJS)"
    )

    # Información técnica del dispositivo
    user_agent = models.TextField(help_text="User agent del navegador/dispositivo")
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="Dirección IP del dispositivo")
    nombre_dispositivo = models.CharField(
        max_length=100, help_text="Nombre descriptivo del dispositivo (generado automáticamente)"
    )

    # Asociación opcional con caja física
    caja_fisica = models.OneToOneField(
        "finanzas.CajaFisica",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dispositivo",
        help_text="Caja física asociada a este dispositivo",
    )

    # Contexto organizacional
    empresa = models.ForeignKey(
        "Empresa",
        on_delete=models.CASCADE,
        related_name="dispositivos",
        help_text="Empresa a la que pertenece el dispositivo",
    )
    sucursal = models.ForeignKey(
        "Sucursal",
        on_delete=models.CASCADE,
        related_name="dispositivos",
        help_text="Sucursal a la que pertenece el dispositivo",
    )

    # Usuario que registró el dispositivo
    creado_por = models.ForeignKey(
        "Usuarios",
        on_delete=models.CASCADE,
        related_name="dispositivos_creados",
        help_text="Usuario que registró este dispositivo",
    )

    # Control de flujo de creación de caja
    preguntar_crear_caja = models.BooleanField(
        default=True, help_text="Si True, preguntar al usuario si quiere crear caja física en próximos logins"
    )
    ultima_pregunta_caja = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que se preguntó sobre crear caja física"
    )

    # Estado y auditoría
    activo = models.BooleanField(default=True, help_text="Si el dispositivo está activo")
    fecha_registro = models.DateTimeField(auto_now_add=True, help_text="Fecha de registro del dispositivo")
    ultimo_login = models.DateTimeField(auto_now=True, help_text="Último login desde este dispositivo")

    class Meta:
        db_table = "core_dispositivo"
        verbose_name = "Dispositivo"
        verbose_name_plural = "Dispositivos"
        unique_together = ["fingerprint", "empresa"]  # Un fingerprint por empresa
        ordering = ["-ultimo_login"]

    def __str__(self):
        return f"{self.nombre_dispositivo} - {self.empresa.nombre_comercial or self.empresa.nombre_legal}"

    @property
    def tiene_caja_fisica(self):
        """Retorna True si el dispositivo tiene una caja física asociada"""
        return self.caja_fisica is not None

    @property
    def puede_crear_caja_fisica(self):
        """Retorna True si el usuario creador tiene permisos para crear cajas físicas"""
        # Por ahora, solo superusuarios pueden crear cajas
        return getattr(self.creado_por, "es_superusuario_innova", False)

    def marcar_no_preguntar_caja(self):
        """Marca que no se debe volver a preguntar sobre crear caja física"""
        self.preguntar_crear_caja = False
        self.ultima_pregunta_caja = timezone.now()
        self.save()

    @classmethod
    def obtener_o_crear(cls, fingerprint, user_agent, ip_address, empresa, sucursal, usuario):
        """
        Obtiene un dispositivo existente o crea uno nuevo.
        """
        dispositivo, created = cls.objects.get_or_create(
            fingerprint=fingerprint,
            empresa=empresa,
            defaults={
                "user_agent": user_agent,
                "ip_address": ip_address,
                "nombre_dispositivo": cls.generar_nombre_dispositivo(user_agent),
                "sucursal": sucursal,
                "creado_por": usuario,
            },
        )

        # Actualizar último login
        dispositivo.ultimo_login = timezone.now()
        dispositivo.save()

        return dispositivo, created

    @staticmethod
    def generar_nombre_dispositivo(user_agent):
        """
        Genera un nombre descriptivo basado en el user agent.
        """
        if "Windows" in user_agent:
            plataforma = "Windows"
        elif "Mac" in user_agent or "macOS" in user_agent:
            plataforma = "macOS"
        elif "Linux" in user_agent:
            plataforma = "Linux"
        elif "Android" in user_agent:
            plataforma = "Android"
        elif "iPhone" in user_agent or "iPad" in user_agent:
            plataforma = "iOS"
        else:
            plataforma = "Desconocido"

        if "Chrome" in user_agent:
            navegador = "Chrome"
        elif "Firefox" in user_agent:
            navegador = "Firefox"
        elif "Safari" in user_agent:
            navegador = "Safari"
        elif "Edge" in user_agent:
            navegador = "Edge"
        else:
            navegador = "Navegador"

        return f"{navegador} en {plataforma}"


# ─────────────────────────────────────────────────────────────────────────────
# CapabilityToken — autorización granular para el MCP server (ADR-003)
# ─────────────────────────────────────────────────────────────────────────────


class CapabilityToken(OmniBaseModel):
    """
    Token de capacidad para acceso externo al MCP server de Omni.

    Principios (ADR-003):
    - Sin acceso por defecto: el tenant activa tokens explícitamente.
    - Scope mínimo: cada token tiene solo los permisos que necesita.
    - Rotación automática: expires_at configurable (default 90 días).
    - Audit log: cada uso queda en LogAuditoria.
    - Revocación inmediata: basta con activo=False.

    Scopes disponibles (formato <modulo>:<operacion>):
      core:read      — leer empresas, usuarios, configuración
      crm:read       — leer clientes
      crm:write      — crear/modificar clientes
      ventas:read    — leer pedidos, facturas, cotizaciones
      ventas:write   — crear/modificar ventas
      inventario:read — leer stock, productos
      cxc:read       — leer cuentas por cobrar, saldos
      cxc:write      — registrar pagos, gestiones de cobranza
      *              — acceso total (solo para tokens internos de sistema)
    """

    # El token en sí: UUID aleatorio, se usa como API key
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Token",
        help_text="UUID generado automáticamente. Se usa como API key.",
    )

    # Tenant owner del token
    empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="capability_tokens",
        verbose_name="Empresa",
    )

    # Descripción legible del propósito del token
    nombre = models.CharField(
        max_length=255,
        verbose_name="Nombre del token",
        help_text="Descripción del agente o sistema que usa este token.",
    )

    # Scopes habilitados (lista JSON de strings)
    scopes = models.JSONField(
        default=list,
        verbose_name="Scopes",
        help_text="Lista de scopes habilitados. Ejemplo: ['crm:read', 'ventas:read']",
    )

    # Expiración — None significa no expira
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Expira en",
        help_text="Fecha de expiración. None = no expira (solo para tokens internos).",
    )

    # Quién creó el token
    creado_por = models.ForeignKey(
        "core.Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tokens_creados",
        verbose_name="Creado por",
    )

    # Último uso (para auditoría)
    ultimo_uso = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Último uso",
    )

    class Meta:
        db_table = "core_capability_token"
        verbose_name = "Capability Token"
        verbose_name_plural = "Capability Tokens"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.nombre} ({str(self.token)[:8]}…) — {self.empresa.nombre_comercial or self.empresa.nombre_legal}"

    def is_expired(self) -> bool:
        """Retorna True si el token ha expirado."""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    def has_scope(self, scope: str) -> bool:
        """Retorna True si el token tiene el scope pedido (o tiene scope '*')."""
        return "*" in self.scopes or scope in self.scopes

    def mark_used(self) -> None:
        """Actualiza ultimo_uso sin disparar auto_now de fecha_actualizacion."""
        self.ultimo_uso = timezone.now()
        self.save(update_fields=["ultimo_uso"])


# ── Contacto Unificado ────────────────────────────────────────────────────────


class Contacto(OmniBaseModel):
    """
    Entidad central de identidad (patrón Odoo).
    Un solo registro puede ser cliente, proveedor, empleado y usuario simultáneamente.
    Reemplaza gradualmente a Cliente, Proveedor y Empleado mediante strangler fig.
    """

    TIPO_PERSONA = [("NATURAL", "Persona Natural"), ("JURIDICA", "Persona Jurídica")]

    id_contacto = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="contactos")

    # Identidad
    tipo_persona = models.CharField(max_length=10, choices=TIPO_PERSONA, default="JURIDICA")
    nombre = models.CharField(max_length=255, help_text="Nombre o Razón Social")
    apellido = models.CharField(max_length=255, blank=True, default="")
    nombre_comercial = models.CharField(max_length=255, blank=True, default="")
    rif = models.CharField(max_length=20, blank=True, default="")
    cedula = models.CharField(max_length=20, blank=True, default="")

    # Contacto
    email = models.EmailField(blank=True, default="")
    telefono = models.CharField(max_length=50, blank=True, default="")
    direccion_fiscal = models.TextField(blank=True, default="")

    # Roles booleanos
    es_cliente = models.BooleanField(default=False)
    es_proveedor = models.BooleanField(default=False)
    es_empleado = models.BooleanField(default=False)
    es_usuario = models.BooleanField(default=False)

    # Campos de cliente
    tipo_credito = models.CharField(
        max_length=10,
        choices=[("CONTADO", "Contado"), ("CREDITO", "Crédito")],
        default="CONTADO",
    )
    limite_credito = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    dias_credito = models.PositiveSmallIntegerField(default=0)
    lista_precio = models.ForeignKey(
        "ventas.ListaPrecio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contactos",
    )

    # Campos de proveedor
    dias_pago = models.PositiveSmallIntegerField(default=30)

    # Enlace opcional a usuario Django
    usuario = models.OneToOneField(
        "Usuarios",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contacto",
    )

    class Meta:
        db_table = "core_contacto"
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        indexes = [
            models.Index(fields=["id_empresa", "es_cliente"]),
            models.Index(fields=["id_empresa", "es_proveedor"]),
            models.Index(fields=["rif"]),
        ]

    def __str__(self):
        if self.nombre_comercial:
            return self.nombre_comercial
        if self.tipo_persona == "NATURAL":
            return f"{self.nombre} {self.apellido}".strip()
        return self.nombre

    @property
    def nombre_completo(self) -> str:
        if self.tipo_persona == "NATURAL":
            return f"{self.nombre} {self.apellido}".strip()
        return self.nombre_comercial or self.nombre


# ─────────────────────────────────────────────────────────────────────────────
# M6: Configuración de flujo de documentos por empresa
# ─────────────────────────────────────────────────────────────────────────────


class ConfiguracionFlujoDocumentos(OmniBaseModel):
    """
    Permite a cada empresa definir qué pasos del ciclo ventas/compras son
    obligatorios y en qué orden deben ejecutarse.

    Ejemplo de uso:
        - VENTAS / COTIZACION / obligatorio=False / orden=1
        - VENTAS / PEDIDO      / obligatorio=True  / orden=2
        - VENTAS / NOTA_ENTREGA/ obligatorio=True  / orden=3
        - VENTAS / FACTURA     / obligatorio=True  / orden=4

    Si 'obligatorio=False' el paso puede omitirse; si no existe registro para
    un paso, se asume obligatorio (comportamiento conservador).
    """

    TIPO_DOCUMENTO = [
        ("VENTAS", "Ciclo de Ventas"),
        ("COMPRAS", "Ciclo de Compras"),
    ]

    PASOS_VENTAS = [
        ("COTIZACION", "Cotización"),
        ("PEDIDO", "Pedido / Nota de Venta"),
        ("NOTA_ENTREGA", "Nota de Entrega"),
        ("FACTURA", "Factura Fiscal"),
    ]

    PASOS_COMPRAS = [
        ("SOLICITUD", "Solicitud de Compra"),
        ("ORDEN_COMPRA", "Orden de Compra"),
        ("RECEPCION", "Recepción de Mercancía"),
        ("FACTURA_COMPRA", "Factura de Compra"),
    ]

    PASOS = PASOS_VENTAS + PASOS_COMPRAS

    id_configuracion = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="configuraciones_flujo",
        db_index=True,
    )
    tipo_documento = models.CharField(max_length=10, choices=TIPO_DOCUMENTO)
    paso = models.CharField(max_length=20, choices=PASOS)
    obligatorio = models.BooleanField(
        default=True,
        help_text="Si es False, este paso puede omitirse en el flujo.",
    )
    orden = models.PositiveSmallIntegerField(
        default=1,
        help_text="Orden relativo de ejecución dentro del tipo de documento.",
    )

    class Meta:
        db_table = "core_configuracion_flujo_documentos"
        unique_together = [["id_empresa", "tipo_documento", "paso"]]
        ordering = ["tipo_documento", "orden"]
        verbose_name = "Configuración de Flujo de Documentos"
        verbose_name_plural = "Configuraciones de Flujo de Documentos"

    def __str__(self):
        estado = "obligatorio" if self.obligatorio else "opcional"
        return f"{self.id_empresa} | {self.tipo_documento} | {self.paso} ({estado}, orden {self.orden})"

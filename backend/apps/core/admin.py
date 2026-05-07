# apps/core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuarios, Roles, Permisos, RolPermisos, UsuarioRoles, RegistroAuditoria, Empresa, Sucursal, Departamento

# Registra tus modelos aquí para que aparezcan en el panel de administración de Django.

# Para el modelo de Usuario personalizado, es una buena práctica usar UserAdmin
# para mantener la funcionalidad existente del admin de usuarios de Django

@admin.register(Usuarios)
class UsuariosAdmin(BaseUserAdmin):
    filter_horizontal = ('empresas', 'sucursales')
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'es_superusuario_omni')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    list_filter = ('is_staff', 'is_active', 'is_superuser', 'es_superusuario_omni', 'groups')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'empresas', 'sucursales')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'es_superusuario_omni', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'empresas', 'sucursales', 'es_superusuario_omni', 'password1', 'password2'),
        }),
    )
    # Puedes añadir tus campos personalizados aquí si los agregaste al modelo Usuarios

@admin.register(Roles)
class RolesAdmin(admin.ModelAdmin):
    list_display = ('nombre_rol', 'descripcion', 'activo', 'fecha_creacion')
    search_fields = ('nombre_rol',)
    list_filter = ('activo',)

@admin.register(Permisos)
class PermisosAdmin(admin.ModelAdmin):
    list_display = ('nombre_permiso', 'descripcion', 'fecha_creacion')
    search_fields = ('nombre_permiso',)

@admin.register(RolPermisos)
class RolPermisosAdmin(admin.ModelAdmin):
    list_display = ('id_rol', 'id_permiso', 'fecha_asignacion')
    list_filter = ('id_rol', 'id_permiso')
    raw_id_fields = ('id_rol', 'id_permiso') # Para selectores más eficientes en muchos registros

@admin.register(UsuarioRoles)
class UsuarioRolesAdmin(admin.ModelAdmin):
    list_display = ('id_usuario', 'id_rol', 'fecha_asignacion')
    list_filter = ('id_usuario', 'id_rol')
    raw_id_fields = ('id_usuario', 'id_rol') # Para selectores más eficientes en muchos registros

@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('fecha_hora_accion', 'tipo_evento', 'id_usuario', 'nombre_modelo_afectado', 'id_registro_afectado')
    list_filter = ('tipo_evento', 'nombre_modelo_afectado', 'id_usuario')
    search_fields = ('tipo_evento', 'nombre_modelo_afectado', 'id_registro_afectado', 'cambios_json__icontains')
    readonly_fields = ('fecha_hora_accion', 'id_usuario', 'direccion_ip', 'navegador_info', 'cambios_json') # No se pueden editar desde el admin

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre_legal', 'nombre_comercial', 'identificador_fiscal', 'activo')
    search_fields = ('nombre_legal', 'nombre_comercial', 'identificador_fiscal')
    list_filter = ('activo',)

@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo_sucursal', 'id_empresa', 'activo')
    search_fields = ('nombre', 'codigo_sucursal')
    list_filter = ('activo', 'id_empresa')
    raw_id_fields = ('id_empresa',)

@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ('nombre_departamento', 'descripcion', 'activo')
    search_fields = ('nombre_departamento',)
    list_filter = ('activo',)

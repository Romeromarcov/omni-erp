from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Allow authenticated users to read; restrict writes to staff only."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff


class IsOwnerOrAdmin(permissions.BasePermission):
    """Allow object access to its owner or staff users."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner_field = getattr(view, "owner_field", "id_usuario")
        owner = getattr(obj, owner_field, None)
        if owner is None:
            return False
        owner_id = getattr(owner, "pk", owner)
        return owner_id == request.user.pk


class HasGranularAccess(permissions.BasePermission):
    """
    Evalúa acceso granular RBAC/ABAC (Módulo × Acción × Ámbito × Alcance).

    Las vistas opt-in declaran ``rbac_modulo = "<modulo>"`` (y opcionalmente
    ``rbac_accion`` o ``rbac_alcance_requerido``). Si la vista no define
    ``rbac_modulo``, permite el paso tras comprobar autenticación.
    """

    _METHOD_ACTION_MAP = {
        "GET": "VER",
        "HEAD": "VER",
        "OPTIONS": "VER",
        "POST": "CREAR",
        "PUT": "EDITAR",
        "PATCH": "EDITAR",
        "DELETE": "ELIMINAR",
    }
    _VIEW_ACTION_MAP = {
        "list": "VER",
        "retrieve": "VER",
        "create": "CREAR",
        "update": "EDITAR",
        "partial_update": "EDITAR",
        "destroy": "ELIMINAR",
        "aprobar": "APROBAR",
        "anular": "ANULAR",
        "exportar": "EXPORTAR",
    }

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False

        modulo = getattr(view, "rbac_modulo", None)
        if not modulo:
            return True

        import uuid

        from apps.core.services_rbac import AMBITOS_RBAC, verificar_acceso
        from apps.core.views import get_empresas_visible

        empresas = get_empresas_visible(request.user)
        raw_empresa_id = (
            request.headers.get("X-Empresa-ID")
            or request.query_params.get("id_empresa")
            or (request.data.get("id_empresa") if isinstance(getattr(request, "data", None), dict) else None)
        )
        empresa = None
        if raw_empresa_id:
            try:
                empresa_uuid = str(uuid.UUID(str(raw_empresa_id).strip()))
            except (ValueError, TypeError):
                self.message = "Identificador de empresa inválido."
                return False
            empresa = empresas.filter(pk=empresa_uuid).first()
        else:
            empresa = empresas.first()
        if empresa is None:
            self.message = "No tiene una empresa activa asignada."
            return False

        view_action = getattr(view, "action", None)
        accion = (
            getattr(view, "rbac_accion", None)
            or (self._VIEW_ACTION_MAP.get(str(view_action)) if view_action else None)
            or self._METHOD_ACTION_MAP.get(request.method, "VER")
        )

        raw_ambito = (
            request.query_params.get("ambito")
            or (request.data.get("ambito") if isinstance(getattr(request, "data", None), dict) else None)
            or "AMBOS"
        )
        ambito = str(raw_ambito).strip().upper()
        if ambito not in AMBITOS_RBAC:
            ambito = "AMBOS"

        alcance_requerido = getattr(view, "rbac_alcance_requerido", None)
        res = verificar_acceso(
            request.user,
            empresa,
            modulo,
            accion,
            ambito=ambito,
            alcance_requerido=alcance_requerido,
        )
        request.rbac_resultado = res
        if not res["permitido"]:
            self.message = f"Acceso denegado ({res['codigo']})."
        return bool(res["permitido"])

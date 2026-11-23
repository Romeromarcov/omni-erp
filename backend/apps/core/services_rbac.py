"""Motor RBAC/ABAC granular por Módulo × Acción × Ámbito (FISCAL/GERENCIAL) × Alcance (Plan 09 Fase 7.1)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import transaction
from django.db.models import Q

from .models import Empresa, PoliticaAccesoRol, RegistroAuditoria, Roles, UsuarioRoles

MODULOS_RBAC: tuple[str, ...] = tuple(code for code, _ in PoliticaAccesoRol.MODULO_CHOICES)
ACCIONES_RBAC: tuple[str, ...] = tuple(code for code, _ in PoliticaAccesoRol.ACCION_CHOICES)
AMBITOS_RBAC: tuple[str, ...] = tuple(code for code, _ in PoliticaAccesoRol.AMBITO_CHOICES)
ALCANCES_RBAC: tuple[str, ...] = tuple(code for code, _ in PoliticaAccesoRol.ALCANCE_CHOICES)

_ALCANCE_RANK: dict[str, int] = {
    "PROPIO": 1,
    "SUCURSAL": 2,
    "ALMACEN": 3,
    "EMPRESA": 4,
}

CAMPOS_SENSIBLES_CATALOGO: list[dict[str, str]] = [
    {"codigo": "costo_unitario", "etiqueta": "Costo unitario", "modulo": "inventario"},
    {"codigo": "costo_reposicion_usd", "etiqueta": "Costo de reposición USD", "modulo": "inventario"},
    {"codigo": "margen", "etiqueta": "Margen de ganancia", "modulo": "ventas"},
    {"codigo": "precio_compra", "etiqueta": "Precio de compra", "modulo": "compras"},
    {"codigo": "bono_gerencial", "etiqueta": "Bono gerencial", "modulo": "nomina"},
    {"codigo": "salario_gerencial", "etiqueta": "Salario gerencial", "modulo": "nomina"},
    {"codigo": "cuenta_gerencial", "etiqueta": "Cuenta gerencial", "modulo": "contabilidad"},
]


def _politicas_contador_fiscal() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mod in ("contabilidad", "fiscal"):
        for acc in ("VER", "CREAR", "EDITAR", "APROBAR", "EXPORTAR", "ANULAR"):
            rows.append(
                {
                    "modulo": mod,
                    "accion": acc,
                    "ambito": "FISCAL",
                    "alcance": "EMPRESA",
                    "permitido": True,
                    "campos_ocultos": [],
                }
            )
    for mod in ("ventas", "compras", "inventario", "finanzas", "tesoreria", "nomina"):
        for acc in ("VER", "EXPORTAR"):
            rows.append(
                {
                    "modulo": mod,
                    "accion": acc,
                    "ambito": "FISCAL",
                    "alcance": "EMPRESA",
                    "permitido": True,
                    "campos_ocultos": [],
                }
            )
    return rows


def _politicas_vendedor() -> list[dict[str, Any]]:
    ocultos_comercial = ["costo_unitario", "costo_reposicion_usd", "margen", "precio_compra"]
    rows: list[dict[str, Any]] = []
    for acc in ("VER", "CREAR", "EDITAR", "EXPORTAR"):
        rows.append(
            {
                "modulo": "ventas",
                "accion": acc,
                "ambito": "AMBOS",
                "alcance": "PROPIO",
                "permitido": True,
                "campos_ocultos": list(ocultos_comercial),
            }
        )
    for acc in ("VER", "CREAR", "EDITAR"):
        rows.append(
            {
                "modulo": "crm",
                "accion": acc,
                "ambito": "AMBOS",
                "alcance": "PROPIO",
                "permitido": True,
                "campos_ocultos": [],
            }
        )
    for acc in ("VER", "CREAR"):
        rows.append(
            {
                "modulo": "pos",
                "accion": acc,
                "ambito": "AMBOS",
                "alcance": "PROPIO",
                "permitido": True,
                "campos_ocultos": list(ocultos_comercial),
            }
        )
    rows.append(
        {
            "modulo": "inventario",
            "accion": "VER",
            "ambito": "AMBOS",
            "alcance": "EMPRESA",
            "permitido": True,
            "campos_ocultos": list(ocultos_comercial),
        }
    )
    return rows


def _politicas_almacenista() -> list[dict[str, Any]]:
    ocultos_inv = ["costo_unitario", "costo_reposicion_usd", "margen", "precio_compra"]
    rows: list[dict[str, Any]] = []
    for acc in ("VER", "CREAR", "EDITAR", "EXPORTAR"):
        rows.append(
            {
                "modulo": "inventario",
                "accion": acc,
                "ambito": "AMBOS",
                "alcance": "ALMACEN",
                "permitido": True,
                "campos_ocultos": list(ocultos_inv),
            }
        )
    for acc in ("VER", "CREAR", "EDITAR"):
        rows.append(
            {
                "modulo": "despacho",
                "accion": acc,
                "ambito": "AMBOS",
                "alcance": "ALMACEN",
                "permitido": True,
                "campos_ocultos": ["costo_unitario", "margen"],
            }
        )
    rows.append(
        {
            "modulo": "compras",
            "accion": "VER",
            "ambito": "AMBOS",
            "alcance": "ALMACEN",
            "permitido": True,
            "campos_ocultos": ["precio_compra"],
        }
    )
    return rows


def _politicas_gerente_general() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mod in MODULOS_RBAC:
        for acc in ACCIONES_RBAC:
            rows.append(
                {
                    "modulo": mod,
                    "accion": acc,
                    "ambito": "AMBOS",
                    "alcance": "EMPRESA",
                    "permitido": True,
                    "campos_ocultos": [],
                }
            )
    return rows


PLANTILLAS_ROL_PREDEFINIDAS: dict[str, dict[str, Any]] = {
    "CONTADOR_FISCAL": {
        "codigo": "CONTADOR_FISCAL",
        "nombre": "Contador Fiscal",
        "descripcion": "Acceso completo a ámbito FISCAL para contabilidad, SENIAT y libros legales.",
        "politicas": _politicas_contador_fiscal(),
    },
    "VENDEDOR": {
        "codigo": "VENDEDOR",
        "nombre": "Vendedor",
        "descripcion": "Operación comercial propia en ventas/CRM/POS ocultando costos y márgenes.",
        "politicas": _politicas_vendedor(),
    },
    "ALMACENISTA": {
        "codigo": "ALMACENISTA",
        "nombre": "Almacenista",
        "descripcion": "Operaciones de inventario y despacho por almacén ocultando costos y precios de compra.",
        "politicas": _politicas_almacenista(),
    },
    "GERENTE_GENERAL": {
        "codigo": "GERENTE_GENERAL",
        "nombre": "Gerente General",
        "descripcion": "Acceso integral dual (Fiscal y Gerencial) con alcance de toda la empresa.",
        "politicas": _politicas_gerente_general(),
    },
}


def obtener_catalogo_rbac() -> dict[str, Any]:
    """Devuelve catálogos de módulos, acciones, ámbitos, alcances, campos sensibles y plantillas."""
    return {
        "modulos": [{"codigo": c, "etiqueta": lbl} for c, lbl in PoliticaAccesoRol.MODULO_CHOICES],
        "acciones": [{"codigo": c, "etiqueta": lbl} for c, lbl in PoliticaAccesoRol.ACCION_CHOICES],
        "ambitos": [{"codigo": c, "etiqueta": lbl} for c, lbl in PoliticaAccesoRol.AMBITO_CHOICES],
        "alcances": [{"codigo": c, "etiqueta": lbl} for c, lbl in PoliticaAccesoRol.ALCANCE_CHOICES],
        "campos_sensibles": CAMPOS_SENSIBLES_CATALOGO,
        "plantillas": [
            {
                "codigo": tpl["codigo"],
                "nombre": tpl["nombre"],
                "descripcion": tpl["descripcion"],
                "total_politicas": len(tpl["politicas"]),
            }
            for tpl in PLANTILLAS_ROL_PREDEFINIDAS.values()
        ],
    }


def _es_admin_total(usuario: Any) -> bool:
    return bool(
        usuario is not None
        and getattr(usuario, "is_authenticated", False)
        and (
            getattr(usuario, "es_superusuario_omni", False)
            or getattr(usuario, "is_superuser", False)
            or getattr(usuario, "is_staff", False)
        )
    )


def _combinar_ambito(actual: str, nuevo: str) -> str:
    if actual == "AMBOS" or nuevo == "AMBOS":
        return "AMBOS"
    if actual != nuevo:
        return "AMBOS"
    return actual


def obtener_matriz_acceso_usuario(usuario: Any, empresa: Empresa) -> dict[str, Any]:
    """Agrega las políticas activas de todos los roles del usuario dentro de ``empresa``."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return {
            "empresa_id": str(empresa.pk),
            "es_admin_total": False,
            "tiene_politicas_explicitas": True,
            "modulos": {},
            "campos_ocultos": {},
        }

    if _es_admin_total(usuario):
        return {
            "empresa_id": str(empresa.pk),
            "es_admin_total": True,
            "tiene_politicas_explicitas": False,
            "modulos": {},
            "campos_ocultos": {},
        }

    rol_ids = list(
        UsuarioRoles.objects.filter(id_usuario=usuario, id_rol__activo=True)
        .filter(Q(id_rol__id_empresa=empresa) | Q(id_rol__id_empresa__isnull=True))
        .values_list("id_rol_id", flat=True)
    )
    if not rol_ids:
        return {
            "empresa_id": str(empresa.pk),
            "es_admin_total": False,
            "tiene_politicas_explicitas": False,
            "modulos": {},
            "campos_ocultos": {},
        }

    politicas = list(
        PoliticaAccesoRol.objects.filter(
            id_empresa=empresa,
            id_rol_id__in=rol_ids,
            activo=True,
        ).order_by("modulo", "accion")
    )
    if not politicas:
        return {
            "empresa_id": str(empresa.pk),
            "es_admin_total": False,
            "tiene_politicas_explicitas": False,
            "modulos": {},
            "campos_ocultos": {},
        }

    agrupadas: dict[tuple[str, str], list[PoliticaAccesoRol]] = {}
    for pol in politicas:
        agrupadas.setdefault((pol.modulo, pol.accion), []).append(pol)

    modulos_out: dict[str, dict[str, dict[str, Any]]] = {}
    ocultos_por_modulo: dict[str, set[str]] = {}

    for (modulo, accion), items in sorted(agrupadas.items()):
        denegada = any(not it.permitido for it in items)
        if denegada:
            entry = {
                "permitido": False,
                "ambito": "AMBOS",
                "alcance": "PROPIO",
                "campos_ocultos": [],
            }
        else:
            ambito_eff = items[0].ambito
            alcance_eff = items[0].alcance
            campos_sets: list[set[str]] = [set(items[0].campos_ocultos or [])]
            for it in items[1:]:
                ambito_eff = _combinar_ambito(ambito_eff, it.ambito)
                if _ALCANCE_RANK.get(it.alcance, 0) > _ALCANCE_RANK.get(alcance_eff, 0):
                    alcance_eff = it.alcance
                campos_sets.append(set(it.campos_ocultos or []))
            interseccion = sorted(set.intersection(*campos_sets)) if campos_sets else []
            entry = {
                "permitido": True,
                "ambito": ambito_eff,
                "alcance": alcance_eff,
                "campos_ocultos": interseccion,
            }
            if interseccion:
                if modulo not in ocultos_por_modulo:
                    ocultos_por_modulo[modulo] = set(interseccion)
                else:
                    ocultos_por_modulo[modulo] &= set(interseccion)

        modulos_out.setdefault(modulo, {})[accion] = entry

    return {
        "empresa_id": str(empresa.pk),
        "es_admin_total": False,
        "tiene_politicas_explicitas": True,
        "modulos": modulos_out,
        "campos_ocultos": {m: sorted(cols) for m, cols in ocultos_por_modulo.items() if cols},
    }


def verificar_acceso(
    usuario: Any,
    empresa: Empresa,
    modulo: str,
    accion: str,
    *,
    ambito: str = "AMBOS",
    alcance_requerido: str | None = None,
) -> dict[str, Any]:
    """Evalúa si ``usuario`` puede ejecutar ``accion`` sobre ``modulo`` con el ámbito/alcance pedidos."""
    mod = str(modulo or "").strip().lower()
    acc = str(accion or "").strip().upper()
    amb = str(ambito or "AMBOS").strip().upper()
    alc_req = str(alcance_requerido).strip().upper() if alcance_requerido else None

    if mod not in MODULOS_RBAC:
        raise ValueError(f"Módulo RBAC inválido: '{modulo}'.")
    if acc not in ACCIONES_RBAC:
        raise ValueError(f"Acción RBAC inválida: '{accion}'.")
    if amb not in AMBITOS_RBAC:
        raise ValueError(f"Ámbito RBAC inválido: '{ambito}'.")
    if alc_req is not None and alc_req not in _ALCANCE_RANK:
        raise ValueError(f"Alcance RBAC inválido: '{alcance_requerido}'.")

    if _es_admin_total(usuario):
        return {
            "permitido": True,
            "codigo": "OK",
            "ambito_efectivo": "AMBOS",
            "alcance_efectivo": "EMPRESA",
            "campos_ocultos": [],
        }

    matriz = obtener_matriz_acceso_usuario(usuario, empresa)
    if not matriz["tiene_politicas_explicitas"]:
        return {
            "permitido": True,
            "codigo": "SIN_POLITICAS_EXPLICITAS",
            "ambito_efectivo": "AMBOS",
            "alcance_efectivo": "EMPRESA",
            "campos_ocultos": [],
        }

    entry = matriz["modulos"].get(mod, {}).get(acc)
    if entry is None or not entry["permitido"]:
        return {
            "permitido": False,
            "codigo": "ACCESO_DENEGADO",
            "ambito_efectivo": "AMBOS",
            "alcance_efectivo": "PROPIO",
            "campos_ocultos": [],
        }

    ambito_eff = entry["ambito"]
    alcance_eff = entry["alcance"]
    ocultos = list(entry["campos_ocultos"])

    if amb in ("FISCAL", "GERENCIAL") and ambito_eff not in (amb, "AMBOS"):
        return {
            "permitido": False,
            "codigo": "AMBITO_NO_AUTORIZADO",
            "ambito_efectivo": ambito_eff,
            "alcance_efectivo": alcance_eff,
            "campos_ocultos": ocultos,
        }

    if alc_req is not None and _ALCANCE_RANK.get(alcance_eff, 0) < _ALCANCE_RANK[alc_req]:
        return {
            "permitido": False,
            "codigo": "ALCANCE_INSUFICIENTE",
            "ambito_efectivo": ambito_eff,
            "alcance_efectivo": alcance_eff,
            "campos_ocultos": ocultos,
        }

    return {
        "permitido": True,
        "codigo": "OK",
        "ambito_efectivo": ambito_eff,
        "alcance_efectivo": alcance_eff,
        "campos_ocultos": ocultos,
    }


def enmascarar_campos_sensibles(data: Any, campos_ocultos: list[str] | set[str] | tuple[str, ...]) -> Any:
    """Elimina recursivamente las llaves sensibles indicadas sin mutar la estructura original."""
    ocultos = {str(c).strip() for c in (campos_ocultos or []) if str(c).strip()}
    copia = deepcopy(data)
    if not ocultos:
        return copia

    def _limpiar(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: _limpiar(v) for k, v in node.items() if k not in ocultos}
        if isinstance(node, list):
            return [_limpiar(item) for item in node]
        return node

    return _limpiar(copia)


@transaction.atomic
def guardar_matriz_rol(
    rol: Roles,
    empresa: Empresa,
    politicas_data: list[dict[str, Any]],
    *,
    usuario: Any = None,
    direccion_ip: str | None = None,
) -> list[PoliticaAccesoRol]:
    """Reemplaza atómicamente la matriz de acceso de ``rol`` para ``empresa`` y deja auditoría."""
    rol_locked = Roles.objects.select_for_update().get(pk=rol.pk)
    if rol_locked.id_empresa_id not in (None, empresa.pk):
        raise ValueError("El rol no pertenece a la empresa indicada.")

    vistas: set[tuple[str, str]] = set()
    nuevas: list[PoliticaAccesoRol] = []
    for item in politicas_data:
        modulo = str(item.get("modulo", "")).strip().lower()
        accion = str(item.get("accion", "")).strip().upper()
        ambito = str(item.get("ambito", "AMBOS")).strip().upper()
        alcance = str(item.get("alcance", "EMPRESA")).strip().upper()
        permitido = bool(item.get("permitido", True))
        campos_ocultos = item.get("campos_ocultos") or []

        clave = (modulo, accion)
        if clave in vistas:
            raise ValueError(f"Política duplicada para ({modulo}, {accion}).")
        vistas.add(clave)

        instancia = PoliticaAccesoRol(
            id_empresa=empresa,
            id_rol=rol_locked,
            modulo=modulo,
            accion=accion,
            ambito=ambito,
            alcance=alcance,
            permitido=permitido,
            campos_ocultos=campos_ocultos,
        )
        # validate_unique=False: la unicidad en el lote ya se validó con `vistas`
        # y los registros previos del rol en `empresa` se reemplazan en esta transacción.
        instancia.full_clean(validate_unique=False)
        nuevas.append(instancia)

    PoliticaAccesoRol.objects.filter(id_empresa=empresa, id_rol=rol_locked).delete()
    creadas: list[PoliticaAccesoRol] = []
    for inst in nuevas:
        inst.save()
        creadas.append(inst)

    RegistroAuditoria.objects.create(
        id_empresa=empresa,
        id_usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        tipo_evento="ACCESO_MATRIZ_ACTUALIZADA",
        modulo_afectado="core",
        nombre_modelo_afectado="PoliticaAccesoRol",
        id_registro_afectado=str(rol_locked.pk),
        descripcion_accion=(
            f"Matriz RBAC/ABAC actualizada para el rol '{rol_locked.nombre_rol}' " f"({len(creadas)} políticas)."
        ),
        cambios_json={
            "id_rol": str(rol_locked.pk),
            "nombre_rol": rol_locked.nombre_rol,
            "total_politicas": len(creadas),
        },
        direccion_ip=direccion_ip,
        resultado_evento="EXITO",
    )
    return creadas


@transaction.atomic
def aplicar_plantilla_rol(
    rol: Roles,
    empresa: Empresa,
    codigo_plantilla: str,
    *,
    usuario: Any = None,
    direccion_ip: str | None = None,
) -> list[PoliticaAccesoRol]:
    """Aplica una plantilla predefinida RBAC/ABAC al rol dentro de ``empresa``."""
    codigo = str(codigo_plantilla or "").strip().upper()
    plantilla = PLANTILLAS_ROL_PREDEFINIDAS.get(codigo)
    if plantilla is None:
        disponibles = ", ".join(sorted(PLANTILLAS_ROL_PREDEFINIDAS))
        raise ValueError(f"Plantilla desconocida '{codigo_plantilla}'. Disponibles: {disponibles}.")
    return guardar_matriz_rol(
        rol,
        empresa,
        list(plantilla["politicas"]),
        usuario=usuario,
        direccion_ip=direccion_ip,
    )

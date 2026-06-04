"""Mapa de superficie del API (A1 del plan "cero dudas").

Introspecta el routing y los modelos y genera matrices versionadas en
docs/audit/ que sirven de checklist de cobertura de auditoría:

  - MAPA_ENDPOINTS.md: ruta → ViewSet → modelo → ¿tenant? → ¿override get_queryset?
  - MAPA_MODELOS.md:   modelo → ¿tenant-aware? → ¿PK UUID? → app

Uso:
    python manage.py mapa_superficie            # escribe los .md
    python manage.py mapa_superficie --check     # falla si están desactualizados (CI)
"""
import io
from pathlib import Path

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.urls import get_resolver

DOCS = Path(__file__).resolve().parents[5] / "docs" / "audit"


def _iter_viewsets():
    seen = set()

    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                yield from walk(p.url_patterns)
                continue
            cls = getattr(getattr(p, "callback", None), "cls", None)
            pattern = str(getattr(p, "pattern", ""))
            if cls is not None and (cls, pattern) not in seen:
                seen.add((cls, pattern))
                yield pattern, cls

    yield from walk(get_resolver().url_patterns)


def _model_de(cls):
    qs = getattr(cls, "queryset", None)
    if qs is not None:
        return qs.model
    ser = getattr(cls, "serializer_class", None)
    return getattr(getattr(ser, "Meta", None), "model", None)


def _es_tenant(model):
    if model is None:
        return False
    # Solo campos concretos (columnas propias del modelo), no relaciones inversas:
    # evita falsos positivos (p.ej. Moneda, referenciada por Empresa.id_moneda_base).
    nombres = {f.name for f in model._meta.concrete_fields}
    return "id_empresa" in nombres or "empresa" in nombres


def _matriz_endpoints() -> str:
    out = io.StringIO()
    out.write("# Mapa de endpoints (A1 — generado por `manage.py mapa_superficie`)\n\n")
    out.write("| Ruta | ViewSet | Modelo | Tenant | Override get_queryset | Permiso |\n")
    out.write("|---|---|---|---|---|---|\n")
    filas = []
    for pattern, cls in _iter_viewsets():
        model = _model_de(cls)
        tenant = "✅" if _es_tenant(model) else "—"
        override = "✅" if "get_queryset" in cls.__dict__ else "—"
        perms = ", ".join(
            getattr(p, "__name__", str(p)) for p in (getattr(cls, "permission_classes", None) or [])
        ) or "—"
        filas.append((pattern, cls.__name__, model.__name__ if model else "—", tenant, override, perms))
    for f in sorted(set(filas)):
        out.write(f"| `{f[0]}` | {f[1]} | {f[2]} | {f[3]} | {f[4]} | {f[5]} |\n")
    out.write(f"\n_Total ViewSets: {len(set(c for _, c, *_ in filas))}_\n")
    return out.getvalue()


def _matriz_modelos() -> str:
    out = io.StringIO()
    out.write("# Mapa de modelos (A1 — generado por `manage.py mapa_superficie`)\n\n")
    out.write("| App | Modelo | Tenant-aware | PK UUID | unique_together |\n")
    out.write("|---|---|---|---|---|\n")
    filas = []
    for model in django_apps.get_models():
        if not model._meta.app_label.startswith(("apps.", "")):
            continue
        if "apps." not in model.__module__:
            continue
        pk = model._meta.pk
        es_uuid = pk.get_internal_type() == "UUIDField"
        ut = model._meta.unique_together
        ut_str = "; ".join("+".join(t) for t in ut) if ut else "—"
        filas.append((
            model._meta.app_label, model.__name__,
            "✅" if _es_tenant(model) else "—",
            "✅" if es_uuid else "—",
            ut_str,
        ))
    for f in sorted(set(filas)):
        out.write(f"| {f[0]} | {f[1]} | {f[2]} | {f[3]} | {f[4]} |\n")
    out.write(f"\n_Total modelos: {len(set(filas))}_\n")
    return out.getvalue()


def _matriz_mcp_celery_commands() -> str:
    import inspect

    out = io.StringIO()
    out.write("# Mapa MCP / Celery / Commands (A1 — generado por `manage.py mapa_superficie`)\n\n")

    # ── Herramientas MCP ──────────────────────────────────────────────────────
    out.write("## Herramientas MCP\n\n| Tool | Módulo |\n|---|---|\n")
    tools = []
    try:
        import apps.core.mcp_server as mcp_mod
        tools = sorted(
            n for n, o in vars(mcp_mod).items()
            if n.startswith("omni_") and inspect.isfunction(o)
        )
    except Exception:  # noqa: BLE001 — introspección best-effort
        pass
    for t in tools:
        out.write(f"| `{t}` | apps.core.mcp_server |\n")
    out.write(f"\n_Total tools MCP: {len(tools)}_\n\n")

    # ── Tareas Celery ─────────────────────────────────────────────────────────
    out.write("## Tareas Celery\n\n| Tarea | Módulo |\n|---|---|\n")
    celery_filas = []
    try:
        import importlib
        from config.celery import app as celery_app
        # Forzar el registro importando cada apps.<app>.tasks (en un contexto sin
        # worker, autodiscover es perezoso y app.tasks no estaría poblado).
        for cfg in django_apps.get_app_configs():
            if not cfg.name.startswith("apps."):
                continue
            try:
                importlib.import_module(f"{cfg.name}.tasks")
            except Exception:  # noqa: BLE001 — sin tasks.py o import fallido: se omite
                continue
        for name, task in celery_app.tasks.items():
            if name.startswith("celery."):
                continue  # tareas internas de Celery
            celery_filas.append((name, getattr(task, "__module__", "—")))
    except Exception:  # noqa: BLE001
        pass
    for name, mod in sorted(set(celery_filas)):
        out.write(f"| `{name}` | {mod} |\n")
    out.write(f"\n_Total tareas Celery: {len(set(celery_filas))}_\n\n")

    # ── Management commands ───────────────────────────────────────────────────
    out.write("## Management commands\n\n| Comando | App |\n|---|---|\n")
    cmd_filas = []
    try:
        from django.core.management import get_commands
        cmd_filas = [
            (name, app) for name, app in get_commands().items()
            if str(app).startswith("apps.")
        ]
    except Exception:  # noqa: BLE001
        pass
    for name, app in sorted(set(cmd_filas)):
        out.write(f"| `{name}` | {app} |\n")
    out.write(f"\n_Total commands: {len(set(cmd_filas))}_\n")
    return out.getvalue()


class Command(BaseCommand):
    help = "Genera las matrices A1 (mapa de superficie) en docs/audit/."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true",
                            help="Falla si las matrices están desactualizadas (para CI).")

    def handle(self, *args, **opts):
        DOCS.mkdir(parents=True, exist_ok=True)
        artefactos = {
            DOCS / "MAPA_ENDPOINTS.md": _matriz_endpoints(),
            DOCS / "MAPA_MODELOS.md": _matriz_modelos(),
            DOCS / "MAPA_MCP_CELERY_COMMANDS.md": _matriz_mcp_celery_commands(),
        }
        if opts["check"]:
            desactualizados = [
                p.name for p, contenido in artefactos.items()
                if not p.exists() or p.read_text(encoding="utf-8") != contenido
            ]
            if desactualizados:
                self.stderr.write(
                    "Matrices A1 desactualizadas: " + ", ".join(desactualizados)
                    + ". Corré `python manage.py mapa_superficie` y commiteá."
                )
                raise SystemExit(1)
            self.stdout.write("Matrices A1 al día.")
            return
        for p, contenido in artefactos.items():
            p.write_text(contenido, encoding="utf-8")
            self.stdout.write(f"Escrito {p.relative_to(DOCS.parents[1])}")

"""
Backfill de cobertura — apps/migracion_datos/management/commands/_importador_base.py
(plan "Cero Dudas").

Se testea con una subclase dummy que escribe ``Almacen`` (modelo simple, multi-tenant)
para verificar la semántica todo-o-nada del importador:

- ``resolver_empresa``: por UUID, identificador_fiscal, nombre_legal; errores de
  vacío, UUID inexistente, ambigüedad y no-encontrado.
- ``handle``: dry-run (no escribe), escritura con --confirm, reversión total cuando
  alguna fila falla (FilaError y excepción inesperada), conteo creado/actualizado.
- ``_leer_filas``: archivo inexistente y archivo vacío sin cabecera.
- Helpers ``requerido`` / ``opcional`` / ``a_decimal``.
"""
import io
from decimal import Decimal

import pytest

from django.core.management.base import CommandError

from apps.almacenes.models import Almacen
from apps.core.models import Empresa
from apps.migracion_datos.management.commands._importador_base import (
    FilaError,
    ImportadorBaseCommand,
    resolver_empresa,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class DummyImportCommand(ImportadorBaseCommand):
    """Importador de prueba: CSV con columnas codigo,nombre → Almacen."""

    nombre_entidad = "almacén"
    requires_system_checks = []  # evitar el system check framework en tests

    def procesar_fila(self, empresa, fila, numero_linea):
        codigo = self.requerido(fila, "codigo")
        nombre = self.opcional(fila, "nombre", default="(sin nombre)")
        if codigo == "BOOM":
            raise RuntimeError("explosión inesperada")
        _, creado = Almacen.objects.update_or_create(
            id_empresa=empresa,
            codigo_almacen=codigo,
            defaults={"nombre_almacen": nombre},
        )
        return "creado" if creado else "actualizado"


def _correr(empresa, archivo, *, confirm=False):
    """Ejecuta el comando dummy capturando stdout/stderr."""
    cmd = DummyImportCommand()
    out, err = io.StringIO(), io.StringIO()
    parser = cmd.create_parser("manage.py", "dummy_import")
    argv = ["--archivo", str(archivo), "--empresa", str(empresa.id_empresa)]
    if confirm:
        argv.append("--confirm")
    options = vars(parser.parse_args(argv))
    options["stdout"] = out
    options["stderr"] = err
    cmd.execute(*options.pop("args", ()), **options)
    return out.getvalue(), err.getvalue()


def _csv(tmp_path, contenido, nombre="datos.csv"):
    p = tmp_path / nombre
    p.write_text(contenido, encoding="utf-8")
    return p


# ── resolver_empresa ──────────────────────────────────────────────────────────


class TestResolverEmpresa:
    def test_sin_identificador(self):
        with pytest.raises(CommandError, match="Debe indicar --empresa"):
            resolver_empresa("")

    def test_por_uuid(self, empresa_a):
        assert resolver_empresa(str(empresa_a.id_empresa)) == empresa_a

    def test_uuid_inexistente(self, empresa_a):
        import uuid
        with pytest.raises(CommandError, match="No existe una empresa"):
            resolver_empresa(str(uuid.uuid4()))

    def test_por_identificador_fiscal(self, empresa_a):
        assert resolver_empresa(empresa_a.identificador_fiscal) == empresa_a

    def test_por_nombre_legal(self, empresa_a):
        assert resolver_empresa("Empresa Alpha S.A.") == empresa_a

    def test_por_nombre_comercial(self, empresa_a):
        empresa_a.nombre_comercial = "Alpha Store"
        empresa_a.save(update_fields=["nombre_comercial"])
        assert resolver_empresa("Alpha Store") == empresa_a

    def test_ambiguedad_lanza(self, empresa_a, empresa_b, moneda_usd):
        Empresa.objects.create(
            nombre_legal="Empresa Alpha S.A.",  # mismo nombre_legal que empresa_a
            identificador_fiscal="J-00000000-0",
            id_moneda_base=moneda_usd,
        )
        with pytest.raises(CommandError, match="coincide con 2 empresas"):
            resolver_empresa("Empresa Alpha S.A.")

    def test_no_encontrada(self, empresa_a):
        with pytest.raises(CommandError, match="No se encontró ninguna empresa"):
            resolver_empresa("No Existe C.A.")


# ── handle: dry-run / confirm / reversión ─────────────────────────────────────


class TestHandle:
    def test_dry_run_no_escribe(self, empresa_a, tmp_path):
        archivo = _csv(tmp_path, "codigo,nombre\nA1,Central\nA2,Norte\n")
        out, err = _correr(empresa_a, archivo, confirm=False)

        assert "DRY-RUN" in out
        assert "Filas OK:     2/2" in out
        assert "Dry-run: no se escribió nada" in out
        assert Almacen.objects.filter(id_empresa=empresa_a).count() == 0

    def test_confirm_escribe_y_cuenta(self, empresa_a, tmp_path):
        # Pre-existente → "actualizado"
        Almacen.objects.create(id_empresa=empresa_a, codigo_almacen="A1", nombre_almacen="Viejo")
        archivo = _csv(tmp_path, "codigo,nombre\nA1,Central\nA2,Norte\n")
        out, err = _correr(empresa_a, archivo, confirm=True)

        assert "ESCRITURA" in out
        assert "Aplicado: 1 creado(s), 1 actualizado(s)." in out
        assert Almacen.objects.filter(id_empresa=empresa_a).count() == 2
        assert Almacen.objects.get(id_empresa=empresa_a, codigo_almacen="A1").nombre_almacen == "Central"

    def test_confirm_con_error_revierte_todo(self, empresa_a, tmp_path):
        """Todo-o-nada: una fila inválida revierte la transacción completa."""
        archivo = _csv(tmp_path, "codigo,nombre\nA1,Central\n,SinCodigo\n")
        out, err = _correr(empresa_a, archivo, confirm=True)

        assert "Filas error:  1" in out
        assert "línea 3: falta el campo requerido 'codigo'." in err
        assert "la transacción fue revertida" in out
        assert Almacen.objects.filter(id_empresa=empresa_a).count() == 0

    def test_excepcion_inesperada_se_reporta(self, empresa_a, tmp_path):
        archivo = _csv(tmp_path, "codigo,nombre\nBOOM,Kaput\n")
        out, err = _correr(empresa_a, archivo, confirm=True)

        assert "Filas OK:     0/1" in out
        assert "error inesperado: explosión inesperada" in err
        assert Almacen.objects.filter(id_empresa=empresa_a).count() == 0

    def test_dry_run_tambien_reporta_errores(self, empresa_a, tmp_path):
        archivo = _csv(tmp_path, "codigo,nombre\n,SinCodigo\nA9,Sur\n")
        out, err = _correr(empresa_a, archivo, confirm=False)

        assert "Filas OK:     1/2" in out
        assert "falta el campo requerido 'codigo'" in err
        assert Almacen.objects.filter(id_empresa=empresa_a).count() == 0


class TestLeerFilas:
    def test_archivo_inexistente(self, empresa_a, tmp_path):
        with pytest.raises(CommandError, match="El archivo no existe"):
            _correr(empresa_a, tmp_path / "nope.csv")

    def test_archivo_vacio_sin_cabecera(self, empresa_a, tmp_path):
        archivo = _csv(tmp_path, "")
        with pytest.raises(CommandError, match="vacío o no tiene cabecera"):
            _correr(empresa_a, archivo)

    def test_archivo_no_utf8(self, empresa_a, tmp_path):
        archivo = tmp_path / "latin1.csv"
        archivo.write_bytes("codigo,nombre\nA1,Almac\xe9n\n".encode("latin-1"))
        with pytest.raises(CommandError, match="No se pudo decodificar el CSV como UTF-8"):
            _correr(empresa_a, archivo)


class TestClaseBase:
    def test_procesar_fila_es_abstracto(self, empresa_a):
        cmd = ImportadorBaseCommand()
        with pytest.raises(NotImplementedError):
            cmd.procesar_fila(empresa_a, {}, 2)


class TestValidarFilaDefault:
    def test_savepoint_revierte_la_escritura(self, empresa_a):
        """validar_fila delega en procesar_fila y revierte el savepoint."""
        from django.db import transaction
        cmd = DummyImportCommand()
        with transaction.atomic():
            cmd.validar_fila(empresa_a, {"codigo": "VAL-1", "nombre": "Temp"}, 2)
            assert not Almacen.objects.filter(codigo_almacen="VAL-1").exists()

    def test_propaga_fila_error(self, empresa_a):
        from django.db import transaction
        cmd = DummyImportCommand()
        with transaction.atomic():
            with pytest.raises(FilaError):
                cmd.validar_fila(empresa_a, {"codigo": ""}, 2)


# ── Helpers de parseo ─────────────────────────────────────────────────────────


class TestHelpers:
    def test_requerido_presente_y_trim(self):
        assert ImportadorBaseCommand.requerido({"x": "  valor  "}, "x") == "valor"

    def test_requerido_faltante(self):
        with pytest.raises(FilaError, match="falta el campo requerido 'x'"):
            ImportadorBaseCommand.requerido({"x": "   "}, "x")
        with pytest.raises(FilaError):
            ImportadorBaseCommand.requerido({}, "x")

    def test_opcional(self):
        assert ImportadorBaseCommand.opcional({"x": " v "}, "x") == "v"
        assert ImportadorBaseCommand.opcional({}, "x") == ""
        assert ImportadorBaseCommand.opcional({"x": "  "}, "x", default="d") == "d"
        assert ImportadorBaseCommand.opcional({"x": None}, "x", default="d") == "d"

    def test_a_decimal(self):
        assert ImportadorBaseCommand.a_decimal("12.50", "monto") == Decimal("12.50")
        assert ImportadorBaseCommand.a_decimal("", "monto") == Decimal("0")
        assert ImportadorBaseCommand.a_decimal(None, "monto") == Decimal("0")
        with pytest.raises(FilaError, match="no es un número válido"):
            ImportadorBaseCommand.a_decimal("abc", "monto")

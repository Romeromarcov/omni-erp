"""
Utilidades compartidas para los management commands de importación (TRACK-1F).

Contiene la clase base ``ImportadorBaseCommand`` que implementa el patrón común:
  - argumentos ``--archivo``, ``--empresa`` y ``--confirm``
  - resolución defensiva de la empresa (UUID pk, luego identificador textual)
  - apertura/parseo de CSV con la librería estándar (sin pandas)
  - reporte estandarizado de filas OK / filas con error (línea + mensaje)
  - dry-run por defecto; escritura real sólo con ``--confirm`` dentro de
    ``transaction.atomic``

Cada comando concreto implementa ``procesar_fila(empresa, fila, numero_linea)``.
"""

import csv
import os
import uuid as uuid_lib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import Empresa


class FilaError(Exception):
    """Error de validación de una fila. El mensaje se reporta al usuario."""


def resolver_empresa(identificador):
    """Resuelve una Empresa por UUID (pk) y, si falla, por identificador textual.

    Intenta en orden:
      1. ``id_empresa`` (UUID pk) si el valor parsea como UUID.
      2. ``identificador_fiscal`` exacto.
      3. ``nombre_comercial`` exacto.
      4. ``nombre_legal`` exacto.

    Lanza ``CommandError`` con un mensaje claro si no encuentra o si hay
    ambigüedad.
    """
    if not identificador:
        raise CommandError("Debe indicar --empresa (UUID o identificador).")

    # 1. UUID pk
    try:
        pk = uuid_lib.UUID(str(identificador))
    except (ValueError, AttributeError, TypeError):
        pk = None
    if pk is not None:
        try:
            return Empresa.objects.get(pk=pk)
        except Empresa.DoesNotExist:
            raise CommandError(f"No existe una empresa con id_empresa={identificador}.")

    # 2-4. Campos textuales
    for campo in ("identificador_fiscal", "nombre_comercial", "nombre_legal"):
        qs = Empresa.objects.filter(**{campo: identificador})
        count = qs.count()
        if count == 1:
            return qs.first()
        if count > 1:
            raise CommandError(
                f"El identificador '{identificador}' coincide con {count} empresas "
                f"por {campo}; use el UUID de la empresa para desambiguar."
            )
    raise CommandError(
        f"No se encontró ninguna empresa para '{identificador}' "
        f"(probado como UUID, identificador_fiscal, nombre_comercial y nombre_legal)."
    )


class ImportadorBaseCommand(BaseCommand):
    """Clase base para los importadores CSV idempotentes de la fase 1.F."""

    # Subclases pueden sobre-escribir para describir el dataset en los reportes.
    nombre_entidad = "registro"

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            type=str,
            required=True,
            help="Ruta al archivo CSV a importar.",
        )
        parser.add_argument(
            "--empresa",
            type=str,
            required=True,
            help="Empresa destino: UUID (id_empresa) o identificador "
            "(identificador_fiscal / nombre_comercial / nombre_legal).",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            default=False,
            help="Ejecuta la escritura real. Sin esta bandera el comando "
            "corre en modo dry-run (sólo valida y reporta).",
        )

    # ── API que las subclases implementan ──────────────────────────────────

    def procesar_fila(self, empresa, fila, numero_linea):
        """Procesa una fila ya parseada (dict). Debe devolver la cadena
        ``"creado"`` o ``"actualizado"`` para el conteo idempotente, o lanzar
        ``FilaError`` con un mensaje legible si la fila es inválida.

        Sólo se invoca en modo escritura (``--confirm``). En dry-run se usa
        ``validar_fila``.
        """
        raise NotImplementedError

    def validar_fila(self, empresa, fila, numero_linea):
        """Valida una fila sin escribir. Por defecto delega en
        ``procesar_fila`` envuelto en un savepoint que se revierte, de modo que
        las subclases no tengan que duplicar lógica. Las subclases pueden
        sobre-escribir si necesitan una validación pura más barata.
        """
        sid = transaction.savepoint()
        try:
            self.procesar_fila(empresa, fila, numero_linea)
        finally:
            transaction.savepoint_rollback(sid)

    # ── Orquestación común ─────────────────────────────────────────────────

    def _leer_filas(self, archivo):
        if not os.path.isfile(archivo):
            raise CommandError(f"El archivo no existe: {archivo}")
        try:
            with open(archivo, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    raise CommandError(f"El archivo está vacío o no tiene cabecera: {archivo}")
                filas = list(reader)
        except UnicodeDecodeError as exc:
            raise CommandError(f"No se pudo decodificar el CSV como UTF-8: {exc}")
        except OSError as exc:
            raise CommandError(f"No se pudo leer el archivo {archivo}: {exc}")
        return filas

    def handle(self, *args, **options):
        archivo = options["archivo"]
        empresa = resolver_empresa(options["empresa"])
        confirmar = options["confirm"]

        filas = self._leer_filas(archivo)
        total = len(filas)
        ok = 0
        creados = 0
        actualizados = 0
        errores = []  # (numero_linea, mensaje)

        modo = "ESCRITURA" if confirmar else "DRY-RUN"
        self.stdout.write(
            f"Importando {total} {self.nombre_entidad}(s) para empresa "
            f"'{empresa}' [{modo}]"
        )

        # La línea 1 del archivo es la cabecera; los datos empiezan en la 2.
        try:
            with transaction.atomic():
                for indice, fila in enumerate(filas):
                    numero_linea = indice + 2
                    try:
                        if confirmar:
                            resultado = self.procesar_fila(empresa, fila, numero_linea)
                            if resultado == "actualizado":
                                actualizados += 1
                            else:
                                creados += 1
                        else:
                            self.validar_fila(empresa, fila, numero_linea)
                        ok += 1
                    except FilaError as exc:
                        errores.append((numero_linea, str(exc)))
                    except Exception as exc:  # noqa: BLE001 - reporte defensivo
                        errores.append((numero_linea, f"error inesperado: {exc}"))

                if errores:
                    # No se persiste nada si alguna fila falló: todo-o-nada.
                    raise _Abortar()
        except _Abortar:
            pass

        # Reporte
        self.stdout.write("")
        for numero_linea, mensaje in errores:
            self.stderr.write(f"  línea {numero_linea}: {mensaje}")

        self.stdout.write(self.style.SUCCESS(f"Filas OK:     {ok}/{total}"))
        if errores:
            self.stdout.write(self.style.ERROR(f"Filas error:  {len(errores)}"))

        if confirmar:
            if errores:
                self.stdout.write(
                    self.style.WARNING(
                        "Se detectaron errores: la transacción fue revertida, "
                        "no se escribió ningún registro."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Aplicado: {creados} creado(s), {actualizados} actualizado(s)."
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run: no se escribió nada. Repita con --confirm para aplicar."
                )
            )

    # ── helpers de parseo para subclases ───────────────────────────────────

    @staticmethod
    def requerido(fila, clave):
        valor = (fila.get(clave) or "").strip()
        if not valor:
            raise FilaError(f"falta el campo requerido '{clave}'.")
        return valor

    @staticmethod
    def opcional(fila, clave, default=""):
        valor = fila.get(clave)
        if valor is None:
            return default
        valor = valor.strip()
        return valor if valor else default

    @staticmethod
    def a_decimal(valor, clave):
        from decimal import Decimal, InvalidOperation

        if valor is None or str(valor).strip() == "":
            return Decimal("0")
        try:
            return Decimal(str(valor).strip())
        except (InvalidOperation, ValueError):
            raise FilaError(f"el campo '{clave}' no es un número válido: '{valor}'.")


class _Abortar(Exception):
    """Señal interna para revertir la transacción cuando hubo errores."""

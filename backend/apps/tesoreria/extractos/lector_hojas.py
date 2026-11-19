"""Lector seguro en memoria de archivos tabulares bancarios (.xlsx, HTML-.xls y .csv).

No añade dependencias externas nuevas al supply-chain:
- ``.xlsx`` (ECMA-376 OpenXML): leído con ``zipfile`` + ``defusedxml.ElementTree``
  respetando coordenadas de columna (``A1``, ``C4``, ``AA10``) para preservar columnas
  dispersas (p. ej. Binance), con defensa contra zip-bombs y XXE.
- ``.xls`` exportados como tabla HTML (p. ej. portal web de Bancamiga en UTF-8 o CP1252):
  leídos con ``html.parser.HTMLParser`` sin acceso a red ni recursos externos.
- ``.csv`` / ``.txt``: leídos con ``csv.reader`` detectando delimitador ``;``, ``,`` o ``\\t``.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
import zlib
from html import escape as xml_escape
from html.parser import HTMLParser
from typing import Any

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

from .modelos_canonicos import ExtractoBancarioError

TAMANO_MAXIMO_ARCHIVO = 10 * 1024 * 1024  # 10 MB comprimido/crudo
TAMANO_MAXIMO_XML_DESCOMPRIMIDO = 32 * 1024 * 1024  # 32 MB descomprimido (anti zip-bomb)
MAX_ENTRADAS_ZIP = 200
MAX_COLUMNAS_HOJA = 256
MAX_FILAS_HOJA = 100_000

_COL_RE = re.compile(r"^([A-Za-z]+)\d+$")
_CTRL_XML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF-"


class _TablaHtmlParser(HTMLParser):
    """Extrae filas ``<tr>`` y celdas ``<td>/<th>`` de tablas HTML bancarias."""

    def __init__(self) -> None:
        super().__init__()
        self.filas: list[list[str]] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l == "tr":
            if len(self.filas) >= MAX_FILAS_HOJA:
                raise ExtractoBancarioError(f"El archivo HTML excede el máximo permitido de {MAX_FILAS_HOJA} filas.")
            self._fila = []
        elif tag_l in ("td", "th") and self._fila is not None:
            if len(self._fila) >= MAX_COLUMNAS_HOJA:
                raise ExtractoBancarioError(
                    f"El archivo HTML excede el máximo permitido de {MAX_COLUMNAS_HOJA} columnas."
                )
            self._celda = []

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in ("td", "th") and self._fila is not None and self._celda is not None:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._celda = None
        elif tag_l == "tr" and self._fila is not None:
            self.filas.append(self._fila)
            self._fila = None

    def handle_data(self, data: str) -> None:
        if self._celda is not None:
            self._celda.append(data)


def _decodificar_texto(contenido: bytes) -> str:
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("cp1252", errors="replace")
    return texto.replace("\x00", "")


def _leer_html(contenido: bytes) -> list[list[Any]]:
    parser = _TablaHtmlParser()
    parser.feed(_decodificar_texto(contenido))
    return [list(f) for f in parser.filas]


def _leer_csv(contenido: bytes) -> list[list[Any]]:
    texto = _decodificar_texto(contenido)
    lineas_muestra = [ln for ln in texto.splitlines()[:10] if ln.strip()]
    delimitador = ","
    if lineas_muestra:
        cab = lineas_muestra[0]
        conteos = {sep: cab.count(sep) for sep in (";", ",", "\t")}
        mejor = max(conteos, key=lambda k: conteos[k])
        if conteos[mejor] > 0:
            delimitador = mejor
    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    filas: list[list[Any]] = []
    try:
        for fila in lector:
            if len(filas) >= MAX_FILAS_HOJA:
                raise ExtractoBancarioError(f"El archivo CSV excede el máximo permitido de {MAX_FILAS_HOJA} filas.")
            if len(fila) > MAX_COLUMNAS_HOJA:
                raise ExtractoBancarioError(
                    f"El archivo CSV excede el máximo permitido de {MAX_COLUMNAS_HOJA} columnas."
                )
            filas.append(list(fila))
    except csv.Error as exc:
        raise ExtractoBancarioError(f"El archivo CSV tiene un formato inválido: {exc}") from exc
    return filas


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _indice_columna_desde_ref(ref: str | None) -> int | None:
    if not ref:
        return None
    m = _COL_RE.match(ref.strip())
    if not m:
        return None
    idx = 0
    for ch in m.group(1).upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
        if idx > MAX_COLUMNAS_HOJA:
            raise ExtractoBancarioError(
                f"Coordenada de columna '{ref}' excede el máximo permitido ({MAX_COLUMNAS_HOJA})."
            )
    return idx - 1


def _extraer_texto_si(elem_si: Any) -> str:
    partes: list[str] = []
    for nodo in elem_si.iter():
        if _local_name(nodo.tag) == "t" and nodo.text:
            partes.append(nodo.text.replace("\x00", ""))
    return "".join(partes)


def _parsear_numero_xml(texto: str) -> int | float | str:
    limpio = texto.replace("\x00", "").strip()
    if not limpio:
        return ""
    if re.fullmatch(r"-?\d+", limpio):
        return int(limpio)
    try:
        return float(limpio)
    except ValueError:
        return texto.replace("\x00", "")


def _leer_entrada_zip_acotada(
    zf: zipfile.ZipFile,
    nombre: str,
    presupuesto_restante: list[int],
) -> bytes:
    """Lee una entrada del ZIP midiendo los bytes reales descomprimidos (anti zip-bomb)."""
    try:
        with zf.open(nombre) as entrada:
            datos = entrada.read(presupuesto_restante[0] + 1)
    except (zlib.error, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise ExtractoBancarioError(
            "El archivo .xlsx está corrupto, cifrado o no puede descomprimirse de forma segura."
        ) from exc

    if len(datos) > presupuesto_restante[0]:
        raise ExtractoBancarioError("El archivo .xlsx descomprimido excede el límite de seguridad de 32 MB.")
    presupuesto_restante[0] -= len(datos)
    return datos


def _parsear_xml_seguro(datos: bytes) -> Any:
    try:
        return SafeET.fromstring(datos)
    except (SafeET.ParseError, DefusedXmlException) as exc:
        raise ExtractoBancarioError(
            "El archivo .xlsx contiene XML malformado o construcciones XML prohibidas."
        ) from exc


def _resolver_primera_hoja_xlsx(
    zf: zipfile.ZipFile,
    nombres: set[str],
    presupuesto_restante: list[int],
) -> tuple[str, int]:
    """Devuelve ``(ruta_xml_hoja, datemode)`` para la primera hoja del libro."""
    datemode = 0
    target_rel: str | None = None
    if "xl/workbook.xml" in nombres:
        wb_root = _parsear_xml_seguro(_leer_entrada_zip_acotada(zf, "xl/workbook.xml", presupuesto_restante))
        rel_id: str | None = None
        for elem in wb_root.iter():
            lname = _local_name(elem.tag)
            if lname == "workbookPr":
                d1904 = str(elem.attrib.get("date1904", "0")).strip().lower()
                if d1904 in ("1", "true"):
                    datemode = 1
            elif lname == "sheet" and rel_id is None:
                for attr_k, attr_v in elem.attrib.items():
                    if attr_k.endswith("}id") or attr_k == "r:id":
                        rel_id = attr_v
                        break
        if rel_id and "xl/_rels/workbook.xml.rels" in nombres:
            rels_root = _parsear_xml_seguro(
                _leer_entrada_zip_acotada(zf, "xl/_rels/workbook.xml.rels", presupuesto_restante)
            )
            for rel in rels_root.iter():
                if _local_name(rel.tag) == "Relationship" and rel.attrib.get("Id") == rel_id:
                    raw_target = rel.attrib.get("Target", "").lstrip("/")
                    if raw_target and not raw_target.startswith("xl/"):
                        raw_target = f"xl/{raw_target}"
                    if raw_target in nombres:
                        target_rel = raw_target
                    break

    if target_rel:
        return target_rel, datemode
    if "xl/worksheets/sheet1.xml" in nombres:
        return "xl/worksheets/sheet1.xml", datemode
    hojas = sorted(n for n in nombres if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    if not hojas:
        raise ExtractoBancarioError("El archivo .xlsx no contiene hojas de cálculo.")
    return hojas[0], datemode


def _leer_xlsx(contenido: bytes) -> tuple[list[list[Any]], int]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile as exc:
        raise ExtractoBancarioError("El archivo .xlsx está corrupto o no es un ZIP válido.") from exc

    presupuesto_restante = [TAMANO_MAXIMO_XML_DESCOMPRIMIDO]
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRADAS_ZIP:
            raise ExtractoBancarioError(
                f"El archivo .xlsx excede el máximo permitido de {MAX_ENTRADAS_ZIP} entradas internas."
            )
        total_declarado = sum(max(0, info.file_size) for info in infos)
        if total_declarado > TAMANO_MAXIMO_XML_DESCOMPRIMIDO:
            raise ExtractoBancarioError("El archivo .xlsx descomprimido excede el límite de seguridad de 32 MB.")

        nombres = {info.filename for info in infos}
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in nombres:
            ss_root = _parsear_xml_seguro(_leer_entrada_zip_acotada(zf, "xl/sharedStrings.xml", presupuesto_restante))
            for child in ss_root:
                if _local_name(child.tag) == "si":
                    shared_strings.append(_extraer_texto_si(child))

        ruta_hoja, datemode = _resolver_primera_hoja_xlsx(zf, nombres, presupuesto_restante)
        sheet_root = _parsear_xml_seguro(_leer_entrada_zip_acotada(zf, ruta_hoja, presupuesto_restante))

    filas: list[list[Any]] = []
    for elem_row in sheet_root.iter():
        if _local_name(elem_row.tag) != "row":
            continue
        if len(filas) >= MAX_FILAS_HOJA:
            raise ExtractoBancarioError(f"El archivo .xlsx excede el máximo permitido de {MAX_FILAS_HOJA} filas.")
        fila: list[Any] = []
        col_cursor = 0
        for celda in elem_row:
            if _local_name(celda.tag) != "c":
                continue
            idx_ref = _indice_columna_desde_ref(celda.attrib.get("r"))
            col_idx = idx_ref if idx_ref is not None else col_cursor
            if col_idx >= MAX_COLUMNAS_HOJA:
                raise ExtractoBancarioError(
                    f"El archivo .xlsx excede el máximo permitido de {MAX_COLUMNAS_HOJA} columnas."
                )
            while len(fila) < col_idx:
                fila.append(None)

            tipo_celda = celda.attrib.get("t", "")
            valor: Any = None
            if tipo_celda == "inlineStr":
                valor = _extraer_texto_si(celda)
            else:
                v_texto: str | None = None
                for sub in celda:
                    if _local_name(sub.tag) == "v":
                        v_texto = (sub.text or "").replace("\x00", "")
                        break
                if v_texto is not None:
                    if tipo_celda == "s":
                        try:
                            ss_idx = int(v_texto)
                            valor = shared_strings[ss_idx] if 0 <= ss_idx < len(shared_strings) else ""
                        except ValueError:
                            valor = ""
                    elif tipo_celda in ("str", "d"):
                        valor = v_texto
                    elif tipo_celda == "b":
                        valor = v_texto.strip() == "1"
                    elif tipo_celda == "e":
                        valor = None
                    else:
                        valor = _parsear_numero_xml(v_texto)

            if col_idx == len(fila):
                fila.append(valor)
            else:
                fila[col_idx] = valor
            col_cursor = col_idx + 1
        filas.append(fila)
    return filas, datemode


def leer_filas_tabular(contenido: bytes, nombre_archivo: str) -> tuple[list[list[Any]], int]:
    """Lee un archivo bancario (``.xlsx``, HTML-``.xls``, ``.csv``) y devuelve ``(filas, datemode)``."""
    nombre_limpio = (nombre_archivo or "extracto").replace("\x00", "")
    if len(contenido) > TAMANO_MAXIMO_ARCHIVO:
        raise ExtractoBancarioError(
            f"El archivo excede el tamaño máximo permitido de {TAMANO_MAXIMO_ARCHIVO // (1024 * 1024)} MB."
        )
    prefijo_raw = contenido.lstrip(b"\xef\xbb\xbf \t\r\n")
    if prefijo_raw[:5] == _PDF_MAGIC or nombre_limpio.lower().endswith(".pdf"):
        raise ExtractoBancarioError(
            f"{nombre_limpio}: los estados de cuenta en PDF no son tabulares; "
            "exporte el extracto desde el portal bancario en formato .xlsx, .xls o .csv."
        )
    prefijo = prefijo_raw[:16].lower()
    if prefijo.startswith((b"<table", b"<!doctype", b"<html", b"<meta", b"<tbody", b"<tr")):
        return _leer_html(contenido), 0
    if contenido[:4] == _ZIP_MAGIC or nombre_limpio.lower().endswith(".xlsx"):
        return _leer_xlsx(contenido)
    if contenido[:8] == _OLE2_MAGIC or nombre_limpio.lower().endswith(".xls"):
        try:
            import xlrd  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ExtractoBancarioError(
                f"{nombre_limpio}: formato binario .xls antiguo (BIFF) no soportado directamente; "
                "exporte el estado de cuenta en formato .xlsx o .csv."
            ) from exc
        try:
            wb = xlrd.open_workbook(file_contents=contenido)
            hoja = wb.sheet_by_index(0)
            return [hoja.row_values(r) for r in range(min(hoja.nrows, MAX_FILAS_HOJA))], int(wb.datemode)
        except Exception as exc:
            raise ExtractoBancarioError(f"{nombre_limpio}: archivo .xls inválido: {exc}") from exc
    return _leer_csv(contenido), 0


def _letra_columna(idx: int) -> str:
    letras: list[str] = []
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letras.append(chr(ord("A") + rem))
    return "".join(reversed(letras))


def construir_xlsx_simple(hojas: list[tuple[str, list[list[Any]]]]) -> bytes:
    """Genera un archivo ``.xlsx`` estándar ECMA-376 en memoria sin dependencias externas."""
    if not hojas:
        raise ValueError("Se requiere al menos una hoja para construir un .xlsx.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(hojas) + 1)
        )
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f"{overrides}</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        sheets_xml = "".join(
            f'<sheet name="{xml_escape(_CTRL_XML_RE.sub("", nombre)[:31])}" ' f'sheetId="{i}" r:id="rId{i}"/>'
            for i, (nombre, _filas) in enumerate(hojas, start=1)
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheets_xml}</sheets></workbook>",
        )
        rels_xml = "".join(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(hojas) + 1)
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels_xml}</Relationships>",
        )

        for idx_hoja, (_nombre, filas) in enumerate(hojas, start=1):
            rows_xml: list[str] = []
            for r_idx, fila in enumerate(filas, start=1):
                celdas_xml: list[str] = []
                for c_idx, val in enumerate(fila):
                    if val is None:
                        continue
                    coord = f"{_letra_columna(c_idx)}{r_idx}"
                    if isinstance(val, bool):
                        celdas_xml.append(f'<c r="{coord}" t="b"><v>{1 if val else 0}</v></c>')
                    elif isinstance(val, int | float):
                        celdas_xml.append(f'<c r="{coord}"><v>{repr(val)}</v></c>')
                    else:
                        texto = xml_escape(_CTRL_XML_RE.sub("", str(val)))
                        celdas_xml.append(
                            f'<c r="{coord}" t="inlineStr"><is><t xml:space="preserve">{texto}</t></is></c>'
                        )
                rows_xml.append(f'<row r="{r_idx}">{"".join(celdas_xml)}</row>')
            zf.writestr(
                f"xl/worksheets/sheet{idx_hoja}.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(rows_xml)}</sheetData></worksheet>',
            )
    return buf.getvalue()

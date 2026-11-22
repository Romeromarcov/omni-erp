"""Generación de códigos QR SVG y PNG para Omni Connect sin nuevas dependencias (S11).

Usa ``reportlab.graphics.barcode.qr.QrCode`` (ya pinneado en ``requirements.txt``)
para construir la matriz QR y codifica:
  - SVG vectorial compacto con runs horizontales (``<path>``).
  - PNG 8-bit escala de grises en Python puro con ``struct`` + ``zlib`` (sin
    depender de ``Pillow`` ni ``rlPyCairo``, 100 % portable Windows/Linux).
"""

from __future__ import annotations

import itertools
import re
import struct
import zlib
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from reportlab.graphics.barcode import qr as reportlab_qr

from .services import ConnectError
from .validators import normalizar_slug, normalizar_uid_chip, validar_slug_perfil, validar_uid_chip

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SAFE_FILENAME_RE = re.compile(r"[^a-z0-9_-]")
_MAX_CONTENIDO_LEN = 2048
_SCALE_MIN = 1
_SCALE_MAX = 32
_BORDER_MIN = 0
_BORDER_MAX = 16


def sanitizar_nombre_archivo_qr(base: str) -> str:
    """Sanitiza un identificador para usarlo en ``Content-Disposition`` sin CRLF ni comillas."""
    limpio = _SAFE_FILENAME_RE.sub("", (base or "").strip().lower())[:80]
    return limpio or "connect-qr"


def construir_url_publica_perfil(
    slug: str,
    *,
    uid: str | None = None,
    origen: str = "QR",
) -> str:
    """Construye la URL pública de un perfil Connect (``<base>/c/<slug>?...``)."""
    if "\x00" in str(slug or ""):
        raise ConnectError("Slug inválido para código QR.")
    slug_norm = normalizar_slug(slug)
    try:
        validar_slug_perfil(slug_norm)
    except DjangoValidationError as exc:
        raise ConnectError("El slug del perfil no es válido para generar código QR.") from exc

    base_url = str(getattr(settings, "CONNECT_PUBLIC_BASE_URL", "https://omni.link") or "https://omni.link").rstrip(
        "/"
    )
    query: dict[str, str] = {}
    if uid is not None and str(uid).strip():
        if "\x00" in str(uid):
            raise ConnectError("UID de tarjeta inválido para código QR.")
        uid_norm = normalizar_uid_chip(str(uid))
        try:
            validar_uid_chip(uid_norm)
        except DjangoValidationError as exc:
            raise ConnectError("El UID de la tarjeta no es válido para generar código QR.") from exc
        query["uid"] = uid_norm
    elif origen:
        origen_limpio = str(origen).strip().upper()
        if origen_limpio in {"NFC", "QR", "ENLACE"}:
            query["origen"] = origen_limpio

    ruta = f"{base_url}/c/{slug_norm}"
    if query:
        return f"{ruta}?{urlencode(query)}"
    return ruta


def _obtener_matriz_qr(contenido: str) -> list[list[bool]]:
    if not isinstance(contenido, str) or "\x00" in contenido:
        raise ConnectError("Contenido inválido para generar código QR.")
    texto = contenido.strip()
    if not texto:
        raise ConnectError("El contenido del código QR no puede estar vacío.")
    if len(texto) > _MAX_CONTENIDO_LEN:
        raise ConnectError("El contenido excede el tamaño máximo permitido para código QR.")

    qr_widget = reportlab_qr.QrCode(texto, qrLevel="M")
    qr_widget.qr.make()
    modulos = qr_widget.qr.modules
    return [[bool(celda) for celda in fila] for fila in modulos]


def _validar_dimensiones(scale: int, border: int) -> tuple[int, int]:
    if isinstance(scale, bool) or isinstance(border, bool):
        raise ConnectError("Los parámetros 'scale' y 'border' deben ser enteros.")
    try:
        scale_val = int(scale)
        border_val = int(border)
    except (TypeError, ValueError) as exc:
        raise ConnectError("Los parámetros 'scale' y 'border' deben ser enteros.") from exc
    scale_int = max(_SCALE_MIN, min(scale_val, _SCALE_MAX))
    border_int = max(_BORDER_MIN, min(border_val, _BORDER_MAX))
    return scale_int, border_int


def generar_qr_svg(contenido: str, *, scale: int = 8, border: int = 4) -> str:
    """Genera un documento SVG limpio y escalable para ``contenido``."""
    scale_int, border_int = _validar_dimensiones(scale, border)
    matriz = _obtener_matriz_qr(contenido)
    modulos = len(matriz)
    lado = (modulos + 2 * border_int) * scale_int

    comandos: list[str] = []
    for fila_idx, fila in enumerate(matriz):
        y = (fila_idx + border_int) * scale_int
        col = 0
        for es_oscuro, grupo in itertools.groupby(fila):
            largo = sum(1 for _ in grupo)
            if es_oscuro:
                x = (col + border_int) * scale_int
                ancho = largo * scale_int
                comandos.append(f"M{x} {y}h{ancho}v{scale_int}h-{ancho}z")
            col += largo

    path_d = "".join(comandos)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lado} {lado}" '
        f'width="{lado}" height="{lado}" shape-rendering="crispEdges" role="img" aria-label="Código QR Omni Connect">'
        '<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<path fill="#000000" d="{path_d}"/>'
        "</svg>"
    )


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def generar_qr_png(contenido: str, *, scale: int = 8, border: int = 4) -> bytes:
    """Genera una imagen PNG (8-bit escala de grises) en Python puro para ``contenido``."""
    scale_int, border_int = _validar_dimensiones(scale, border)
    matriz = _obtener_matriz_qr(contenido)
    modulos = len(matriz)
    total_modulos = modulos + 2 * border_int
    lado = total_modulos * scale_int

    fila_blanca = b"\x00" + (b"\xff" * lado)
    borde_lateral = b"\xff" * (border_int * scale_int)
    pixel_negro = b"\x00" * scale_int
    pixel_blanco = b"\xff" * scale_int

    scanlines: list[bytes] = []
    for _ in range(border_int * scale_int):
        scanlines.append(fila_blanca)

    for fila in matriz:
        contenido_fila = b"".join(pixel_negro if oscuro else pixel_blanco for oscuro in fila)
        linea = b"\x00" + borde_lateral + contenido_fila + borde_lateral
        for _ in range(scale_int):
            scanlines.append(linea)

    for _ in range(border_int * scale_int):
        scanlines.append(fila_blanca)

    raw_data = b"".join(scanlines)
    ihdr = struct.pack(">IIBBBBB", lado, lado, 8, 0, 0, 0, 0)
    idat = zlib.compress(raw_data, level=9)
    return _PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")

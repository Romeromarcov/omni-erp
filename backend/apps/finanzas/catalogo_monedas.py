"""Catálogo base de monedas (global, compartido por todas las empresas).

``Moneda`` es un catálogo global (``codigo_iso`` único, ``empresa=None``). Varias piezas asumen que
existen ``USD`` y ``VES``: la sincronización de tasas (``integration_hub.sync_tasas_ve``), la captura
de CxC Lubrikca y los widgets de cartera. Sin sembrarlas, un entorno nuevo (staging, producción
reprovisionada) arranca con esas funciones inertes o fallando.

``sembrar_catalogo_monedas`` es **idempotente y no destructivo**: crea lo que falta y completa solo los
campos que sigan en su valor "placeholder" (p. ej. la moneda base que ``seed_empresa_inicial`` crea con
``nombre == codigo``). Nunca pisa un valor que alguien haya editado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Moneda

# (codigo_iso, nombre, simbolo, pais_codigo_iso, pais_nombre, tipo_moneda, decimales)
CATALOGO_BASE: tuple[tuple[str, str, str, str | None, str | None, str, int], ...] = (
    ("USD", "Dólar estadounidense", "$", "USA", "Estados Unidos", "fiat", 2),
    ("VES", "Bolívar venezolano", "Bs", "VEN", "Venezuela", "fiat", 2),
    ("EUR", "Euro", "€", None, "Zona euro", "fiat", 2),
    # Stablecoin ligada al dólar: en Omni se opera con 2 decimales, como el resto de montos.
    ("USDT", "Tether", "USDT", None, None, "crypto", 2),
)


@dataclass
class ResultadoSiembra:
    """Qué hizo la siembra, por código ISO."""

    creadas: list[str] = field(default_factory=list)
    completadas: list[str] = field(default_factory=list)
    sin_cambios: list[str] = field(default_factory=list)


def _es_placeholder(valor, codigo: str, *, recortado: bool = False) -> bool:
    """Vacío, o igual al código (``USD``/``USD``): lo deja un seed mínimo, no una edición humana."""
    if valor in (None, ""):
        return True
    esperado = codigo[:5] if recortado else codigo
    return str(valor).strip().upper() == esperado.upper()


def sembrar_catalogo_monedas() -> ResultadoSiembra:
    """Crea las monedas base que falten y completa las que estén a medias. Idempotente."""
    from apps.core import rls

    resultado = ResultadoSiembra()
    with rls.rls_bypass():
        for codigo, nombre, simbolo, pais_iso, pais_nombre, tipo, decimales in CATALOGO_BASE:
            moneda, creada = Moneda.objects.get_or_create(
                codigo_iso=codigo,
                defaults={
                    "nombre": nombre,
                    "simbolo": simbolo,
                    "pais_codigo_iso": pais_iso,
                    "pais_nombre": pais_nombre,
                    "tipo_moneda": tipo,
                    "decimales": decimales,
                    "activo": True,
                    "es_generica": True,
                    "es_publica": True,
                },
            )
            if creada:
                resultado.creadas.append(codigo)
                continue

            # Candidatos: solo los campos vacíos o aún en su valor placeholder. Un candidato solo cuenta
            # como cambio si el valor realmente difiere: p. ej. USDT tiene símbolo "USDT" (igual a su código),
            # que es a la vez placeholder y valor correcto, y no debe contarse como "completada" cada vez.
            candidatos: dict[str, object] = {}
            if _es_placeholder(moneda.nombre, codigo):
                candidatos["nombre"] = nombre
            if _es_placeholder(moneda.simbolo, codigo, recortado=True):
                candidatos["simbolo"] = simbolo
            if moneda.pais_codigo_iso in (None, "") and pais_iso:
                candidatos["pais_codigo_iso"] = pais_iso
            if moneda.pais_nombre in (None, "") and pais_nombre:
                candidatos["pais_nombre"] = pais_nombre
            cambios = {campo: valor for campo, valor in candidatos.items() if getattr(moneda, campo) != valor}

            if cambios:
                for campo, valor in cambios.items():
                    setattr(moneda, campo, valor)
                moneda.save(update_fields=list(cambios))
                resultado.completadas.append(codigo)
            else:
                resultado.sin_cambios.append(codigo)
    return resultado

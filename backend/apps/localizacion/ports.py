"""
Puertos de localización (ADR-007).

El núcleo es agnóstico de país y solo conoce estas interfaces abstractas. Cada
localización (ej. ``localizacion_ve``) implementa los puertos que provee y los
registra vía ``registry.register``. El núcleo obtiene la implementación con
``services.get_localizacion(empresa)``.

Seis puertos: tres de la capa legal (impuestos, documento legal, nómina, libro
legal) y dos de la capa de mercado (tasas, métodos de pago). Implementaciones
"no-op" sirven cuando una capa está desactivada para la empresa.
"""
from abc import ABC, abstractmethod
from decimal import Decimal


# ── Capa legal ─────────────────────────────────────────────────────────────


class MotorImpuestos(ABC):
    """Calcula los impuestos de una operación (IVA, IGTF, retenciones)."""

    @abstractmethod
    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict:
        ...


class GeneradorDocumentoLegal(ABC):
    """Emite el documento fiscal legal del país (factura, nota de crédito)."""

    @abstractmethod
    def emitir(self, *, documento, empresa) -> dict:
        ...


class CalculadoraNomina(ABC):
    """Conceptos y deducciones obligatorias de nómina del país."""

    @abstractmethod
    def calcular(self, *, empleado, periodo, empresa) -> dict:
        ...


class LibroLegal(ABC):
    """Libros/declaraciones para el fisco (p. ej. libros SENIAT)."""

    @abstractmethod
    def generar(self, *, empresa, periodo, tipo: str):
        ...


# ── Capa de mercado ──────────────────────────────────────────────────────────


class ProveedorTasas(ABC):
    """Obtiene tasas de cambio del mercado."""

    @abstractmethod
    def obtener_tasa(self, *, origen: str, destino: str) -> Decimal | None:
        ...


class MetodosPagoLocales(ABC):
    """Métodos de pago propios del país/mercado."""

    @abstractmethod
    def listar(self, *, empresa) -> list[dict]:
        ...


# ── No-ops (capa desactivada) ────────────────────────────────────────────────


class MotorImpuestosNoOp(MotorImpuestos):
    """Sin impuestos: empresa sin localización legal activa."""

    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict:
        cero = Decimal("0")
        return {"iva": cero, "igtf": cero, "total_impuestos": cero}

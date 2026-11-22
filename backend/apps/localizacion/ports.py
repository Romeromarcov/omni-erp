"""
Puertos de localización (ADR-007).

El núcleo es agnóstico de país y solo conoce estas interfaces abstractas. Cada
localización (ej. ``localizacion_ve``) implementa los puertos que provee y los
registra vía ``registry.register``. El núcleo obtiene la implementación con
``services.get_localizacion(empresa)``.

Seis puertos: cuatro de la capa legal (impuestos, documento legal, nómina, libro
legal) y dos de la capa de mercado (tasas, métodos de pago). Implementaciones
"no-op" sirven cuando una capa está desactivada para la empresa.
"""

from abc import ABC, abstractmethod
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


# ── Capa legal ─────────────────────────────────────────────────────────────


class MotorImpuestos(ABC):
    """Calcula los impuestos de una operación (IVA, IGTF, retenciones)."""

    @abstractmethod
    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict: ...


class GeneradorDocumentoLegal(ABC):
    """Emite el documento fiscal legal del país (factura, nota de crédito)."""

    @abstractmethod
    def emitir(self, *, documento, empresa) -> dict: ...


class CalculadoraNomina(ABC):
    """Conceptos y deducciones obligatorias de nómina del país."""

    @abstractmethod
    def calcular(self, *, empleado, periodo, empresa, contexto: dict | None = None) -> dict: ...


class LibroLegal(ABC):
    """Libros/declaraciones para el fisco (p. ej. libros SENIAT)."""

    @abstractmethod
    def generar(self, *, empresa, periodo, tipo: str, formato: str = "txt"): ...


# ── Capa de mercado ──────────────────────────────────────────────────────────


class ProveedorTasas(ABC):
    """Obtiene tasas de cambio del mercado."""

    @abstractmethod
    def obtener_tasa(self, *, origen: str, destino: str, empresa: Any = None) -> Decimal | None: ...


class MetodosPagoLocales(ABC):
    """Métodos de pago propios del país/mercado."""

    @abstractmethod
    def listar(self, *, empresa) -> list[dict]: ...


# ── No-ops (capa desactivada) ────────────────────────────────────────────────


class MotorImpuestosNoOp(MotorImpuestos):
    """Sin impuestos: empresa sin localización legal activa."""

    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict:
        cero = Decimal("0")
        return {"iva": cero, "igtf": cero, "total_impuestos": cero}


class GeneradorDocumentoLegalNoOp(GeneradorDocumentoLegal):
    """Sin documento fiscal país-específico: respuesta neutra sin pie legal."""

    def emitir(self, *, documento, empresa) -> dict:
        cero = Decimal("0")
        if isinstance(documento, dict):
            tipo = str(documento.get("tipo_documento") or "GENERICO")
        else:
            tipo = str(getattr(documento, "tipo_documento", None) or "GENERICO")
        pais = str(getattr(empresa, "pais_codigo_iso", None) or "").strip().upper()
        return {
            "tipo_documento": tipo,
            "numero_documento": "",
            "numero_control": "",
            "fecha_emision": "",
            "moneda": "",
            "subtotal": cero,
            "iva": cero,
            "igtf": cero,
            "exento": cero,
            "total": cero,
            "requiere_pie_legal_seniat": False,
            "pais": pais,
            "noop": True,
        }


class CalculadoraNominaNoOp(CalculadoraNomina):
    """Sin reglas legales de nómina de país: cálculo salarial básico sin reglas LOTTT."""

    def calcular(self, *, empleado, periodo, empresa, contexto: dict | None = None) -> dict:
        cero = Decimal("0")
        salario_periodo = cero
        otras_asig = cero
        otras_ded = cero
        if contexto and contexto.get("salario_mensual") is not None:
            datos = dict(contexto.get("datos") or {})
            dias = int(datos.get("dias_trabajados", 30))
            salario_mensual = Decimal(str(contexto["salario_mensual"]))
            salario_periodo = (salario_mensual * Decimal(dias) / Decimal("30")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            otras_asig = Decimal(str(datos.get("otras_asignaciones", cero))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            otras_ded = Decimal(str(datos.get("otras_deducciones", cero))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        total_asignaciones = salario_periodo + otras_asig
        total_deducciones = otras_ded
        neto_pagar = max(total_asignaciones - total_deducciones, cero)
        return {
            "salario_periodo": salario_periodo,
            "monto_horas_extra_diurnas": cero,
            "monto_horas_extra_nocturnas": cero,
            "monto_bono_nocturno": cero,
            "otras_asignaciones": otras_asig,
            "total_devengado_salarial": total_asignaciones,
            "cestaticket": cero,
            "sso": cero,
            "faov": cero,
            "rpe": cero,
            "islr": cero,
            "otras_deducciones": otras_ded,
            "total_deducciones": total_deducciones,
            "total_asignaciones": total_asignaciones,
            "neto_pagar": neto_pagar,
            "provision_utilidades": cero,
            "provision_vacaciones": cero,
            "provision_bono_vacacional": cero,
            "provision_prestaciones": cero,
            "aporte_patronal_sso": cero,
            "aporte_patronal_faov": cero,
            "aporte_patronal_inces": cero,
            "aporte_patronal_rpe": cero,
            "total_aportes_patronales": cero,
            "noop": True,
        }


class LibroLegalNoOp(LibroLegal):
    """Sin libros fiscales de país: devuelve contenido vacío."""

    def generar(self, *, empresa, periodo, tipo: str, formato: str = "txt") -> str | bytes:
        if str(formato or "txt").strip().lower() == "pdf":
            return b""
        return ""


class ProveedorTasasNoOp(ProveedorTasas):
    """Sin proveedor de tasas de mercado: devuelve None."""

    def obtener_tasa(self, *, origen: str, destino: str, empresa: Any = None) -> Decimal | None:
        return None


class MetodosPagoLocalesNoOp(MetodosPagoLocales):
    """Sin métodos de pago específicos del mercado local."""

    def listar(self, *, empresa) -> list[dict]:
        return []

"""
M8-T6: Test de concurrencia para correlativos fiscales.

Verifica que `siguiente_numero` es thread-safe y no genera duplicados
cuando múltiples hilos solicitan correlativos simultáneamente.

Nota: Los tests con `transaction_db` (REAL COMMIT) se usan aquí para que
los locks SELECT FOR UPDATE funcionen correctamente entre hilos.
"""

import threading
from collections import Counter

import pytest
from django.db import connections


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def moneda_ves_conc(db):
    from apps.finanzas.models import Moneda

    return Moneda.objects.create(
        nombre="Bolívar Digital",
        codigo_iso="VES",
        simbolo="Bs.",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def empresa_conc(db, moneda_ves_conc):
    from apps.core.models import Empresa

    return Empresa.objects.create(
        nombre_legal="Empresa Concurrencia Test S.A.",
        identificador_fiscal="J-99999999-9",
        email_contacto="conc@test.com",
        activo=True,
        id_moneda_base=moneda_ves_conc,
    )


# ── Tests de unicidad secuencial ──────────────────────────────────────────────


@pytest.mark.django_db
class TestCorrelativoUnicidad:
    """Tests de unicidad sin threads (verifican la lógica core)."""

    def test_secuencia_incremental_sin_gaps(self, empresa_conc):
        """Verifica que los correlativos son secuenciales y sin huecos."""
        from apps.fiscal.services import siguiente_numero

        n = 20
        resultados = [siguiente_numero(empresa_conc, "FACTURA") for _ in range(n)]

        # Todos únicos
        assert len(set(resultados)) == n, f"Duplicados: {Counter(resultados).most_common(3)}"

        # Secuenciales empezando en 1
        esperados = [f"{i:08d}" for i in range(1, n + 1)]
        assert resultados == esperados

    def test_secuencias_independientes_por_tipo(self, empresa_conc):
        """Tipos distintos tienen contadores independientes."""
        from apps.fiscal.services import siguiente_numero

        f1 = siguiente_numero(empresa_conc, "FACTURA")
        nc1 = siguiente_numero(empresa_conc, "NOTA_CREDITO")
        f2 = siguiente_numero(empresa_conc, "FACTURA")
        nc2 = siguiente_numero(empresa_conc, "NOTA_CREDITO")

        assert f1 == "00000001"
        assert nc1 == "00000001"  # secuencia independiente
        assert f2 == "00000002"
        assert nc2 == "00000002"

    def test_secuencias_independientes_por_empresa(self, db, empresa_conc, moneda_ves_conc):
        """Empresas distintas tienen contadores independientes."""
        from apps.core.models import Empresa
        from apps.fiscal.services import siguiente_numero

        empresa_b = Empresa.objects.create(
            nombre_legal="Empresa B Concurrencia S.A.",
            identificador_fiscal="J-88888888-8",
            email_contacto="b@test.com",
            activo=True,
            id_moneda_base=moneda_ves_conc,
        )

        n1_a = siguiente_numero(empresa_conc, "FACTURA")
        n1_b = siguiente_numero(empresa_b, "FACTURA")
        n2_a = siguiente_numero(empresa_conc, "FACTURA")

        assert n1_a == "00000001"
        assert n1_b == "00000001"  # empresa B empieza en 1
        assert n2_a == "00000002"


# ── Tests de concurrencia con threads ─────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
class TestCorrelativoConcurrencia:
    """
    Tests con transacciones reales para verificar thread-safety del SELECT FOR UPDATE.

    NOTA: Se necesita transaction=True para que los commits de cada hilo sean visibles
    a los demás y el mecanismo de lock funcione correctamente.
    """

    def test_threads_producen_correlativos_unicos(self, empresa_conc):
        """
        Lanza N hilos simultáneos que solicitan correlativos.
        Verifica que todos los correlativos generados son únicos.
        """
        from apps.fiscal.services import siguiente_numero

        N_HILOS = 10
        resultados = []
        errores = []
        lock = threading.Lock()

        def obtener_numero():
            try:
                num = siguiente_numero(empresa_conc, "FACTURA_THREAD")
                with lock:
                    resultados.append(num)
            except Exception as exc:
                with lock:
                    errores.append(str(exc))

        hilos = [threading.Thread(target=obtener_numero) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=10)

        # Cerrar conexiones de threads para evitar el warning "DB en uso" al teardown
        for conn in connections.all():
            conn.close()

        assert not errores, f"Errores en hilos: {errores}"
        assert len(resultados) == N_HILOS, f"Se esperaban {N_HILOS} resultados, hay {len(resultados)}"

        # Todos únicos — la propiedad más crítica
        assert len(set(resultados)) == N_HILOS, (
            f"¡DUPLICADOS DETECTADOS! Correlativos generados: {sorted(resultados)}\n"
            f"Duplicados: {[k for k, v in Counter(resultados).items() if v > 1]}"
        )

    def test_rango_numerico_correcto_bajo_concurrencia(self, empresa_conc):
        """
        Los correlativos generados por threads deben cubrir exactamente el rango [1..N].
        """
        from apps.fiscal.services import siguiente_numero

        N_HILOS = 5
        resultados = []
        lock = threading.Lock()

        def obtener_numero():
            try:
                num = siguiente_numero(empresa_conc, "NOTA_DEBITO_THREAD")
                with lock:
                    resultados.append(num)
            except Exception:
                pass

        hilos = [threading.Thread(target=obtener_numero) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=10)

        # Verificar que son N únicos en el rango 1..N
        nums_int = sorted(int(r) for r in resultados)
        assert nums_int == list(range(1, N_HILOS + 1)), (
            f"Rango incorrecto: {nums_int}, esperado: {list(range(1, N_HILOS + 1))}"
        )

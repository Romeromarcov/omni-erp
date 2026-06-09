"""
Conftest raíz de ``backend/`` — configuración transversal a toda la suite.

Su única responsabilidad hoy es **estabilizar Hypothesis** bajo carga paralela.

Por qué: los property-based tests (``tests/unit/test_property_*.py``,
``tests_api/test_property_*.py``) corren en CI con ``pytest -n auto``. El
``deadline`` por defecto de Hypothesis (200 ms por ejemplo) mide tiempo de pared,
no de CPU; cuando varios workers de xdist compiten por la CPU, un ejemplo trivial
(p. ej. una resta de ``Decimal``) puede superar 200 ms de forma esporádica y
Hypothesis lo reporta como ``DeadlineExceeded`` → fallo intermitente del gate sin
ningún bug real detrás (observado en ``test_score_monotono_en_cada_entrada``, cuya
propiedad es estrictamente monótona y no admite contraejemplo matemático).

La cura idiomática es desactivar el ``deadline`` (medir corrección, no latencia) y
suprimir los health-checks de lentitud, que son ruido bajo paralelismo. Se registra
un perfil ``ci`` y se carga siempre, de modo que aplique a todos los property tests
sin tener que decorar cada uno.
"""
from hypothesis import HealthCheck, settings

settings.register_profile(
    "ci",
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")

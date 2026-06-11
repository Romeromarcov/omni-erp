"""Runner de mutation testing que normaliza el exit code de pytest.

Por qué existe: mutmut clasifica un mutante como *killed* cuando el runner sale
con código 1, pero pytest usa **otros códigos** para fallos igual de letales —
en particular **2 = error de colección** (p. ej. un mutante que rompe una
constante de módulo, `Decimal("XX0.01XX")`, revienta el *import* del módulo
mutado). mutmut contaba esos mutantes como *survived*, **subestimando el score**
(verificado el 2026-06-09: en nómina LOTTT 35+ "sobrevivientes" eran mutantes de
la tabla de tramos ISLR que en realidad rompen el import y matan a TODA la
suite).

Este wrapper ejecuta pytest y traduce cualquier salida distinta de 0 a 1, que es
lo que mutmut entiende como "los tests detectaron el mutante".

Uso (como --runner de mutmut):
    python scripts/mut_runner.py <archivo_de_tests> [args extra de pytest]
"""
import subprocess
import sys

r = subprocess.call(
    [sys.executable, "-m", "pytest", *sys.argv[1:], "-x", "-q", "--no-cov", "-p", "no:cacheprovider"]
)
sys.exit(0 if r == 0 else 1)

"""
Tests de fail-closed de configuración (H-SEC-1, H-SEC-2).

Se ejecutan en subprocesos con un cwd limpio (sin ``.env``) y ``PYTHONPATH``
apuntando al backend, para reproducir el entorno de CI/producción donde la
config viene SOLO de variables de entorno. Así ``dotenv`` no enmascara la
ausencia de SECRET_KEY. No contaminan los settings ya cargados por pytest.
"""

import os
import subprocess
import sys
from pathlib import Path
import pytest

pytestmark = pytest.mark.unit

# backend/ está dos niveles arriba (tests/unit/ → tests/ → backend/).
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _import_settings(env_overrides, tmp_cwd):
    """Importa config.settings en un subproceso con env y cwd limpio."""
    env = os.environ.copy()
    # Aislar de cualquier .env del repo: cwd limpio + PYTHONPATH explícito.
    env["PYTHONPATH"] = str(BACKEND_DIR)
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=str(tmp_cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def test_django_env_invalido_falla(tmp_path):
    """H-SEC-1: DJANGO_ENV='production' (typo) no cae a dev — explota."""
    result = _import_settings({"DJANGO_ENV": "production"}, tmp_path)
    assert result.returncode != 0, "DJANGO_ENV inválido debería abortar la importación."
    assert "DJANGO_ENV debe ser" in result.stderr


def test_django_env_ausente_falla(tmp_path):
    """H-SEC-1: DJANGO_ENV sin definir explota (no default silencioso)."""
    result = _import_settings({"DJANGO_ENV": None}, tmp_path)
    assert result.returncode != 0
    assert "DJANGO_ENV debe ser" in result.stderr


def test_secret_key_ausente_en_dev_falla(tmp_path):
    """H-SEC-2: sin SECRET_KEY explícito, ni dev arranca con clave débil."""
    result = _import_settings({"DJANGO_ENV": "dev", "SECRET_KEY": None}, tmp_path)
    assert result.returncode != 0, "Arrancar sin SECRET_KEY debería abortar."
    assert "SECRET_KEY" in result.stderr


def test_dev_arranca_con_config_correcta(tmp_path):
    """Sanity: con DJANGO_ENV=dev y SECRET_KEY presente, importa sin error."""
    result = _import_settings(
        {"DJANGO_ENV": "dev", "SECRET_KEY": "test-key-suficientemente-larga-para-dev"}, tmp_path
    )
    assert result.returncode == 0, f"Importación falló inesperadamente: {result.stderr}"

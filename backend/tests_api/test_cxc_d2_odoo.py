"""
Plan D — Fase D2: conexión Odoo real y tooling de provisión/validación.

No requiere un Odoo vivo: el conector se mockea. Cubre:
  - El fix de import de la task sync_cartera_odoo (estaba rota: importaba de
    apps.cuentas_por_cobrar.services.* en vez de services_*).
  - El comando configurar_conector_odoo (provisión + cifrado + datasource).
  - El comando validar_conector_odoo (test_connection + muestra de cartera).
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.integration_hub.connectors.base import TestConnectionResult as ConnResult
from apps.integration_hub.models import ConectorInstancia

pytestmark = pytest.mark.django_db


# ── Fix de la task sync_cartera_odoo ─────────────────────────────────────────


class TestSyncCarteraOdooTask:
    def test_task_importa_y_corre_native(self, empresa_a):
        """Regresión: la task fallaba con ImportError por rutas services.*
        inexistentes. Ahora corre y cachea el aging (empresa native, sin CxC)."""
        from apps.integration_hub.tasks import sync_cartera_odoo

        resultado = sync_cartera_odoo(str(empresa_a.id_empresa))
        assert resultado == {"empresa_id": str(empresa_a.id_empresa), "partidas": 0}

    def test_fan_out_solo_encola_tenants_odoo(self, empresa_a, empresa_b):
        """sync_cartera_odoo_todos encola solo los tenants con datasource=odoo."""
        from apps.configuracion_motor.models import ParametroSistema
        from apps.integration_hub import tasks

        ParametroSistema.objects.create(
            id_empresa=empresa_a,
            codigo_parametro="cxc.datasource",
            nombre_parametro="ds",
            valor_parametro="odoo",
            tipo_dato="TEXTO",
            activo=True,
        )
        ParametroSistema.objects.create(
            id_empresa=empresa_b,
            codigo_parametro="cxc.datasource",
            nombre_parametro="ds",
            valor_parametro="native",
            tipo_dato="TEXTO",
            activo=True,
        )
        with patch.object(tasks.sync_cartera_odoo, "delay") as mock_delay:
            resultado = tasks.sync_cartera_odoo_todos()
        assert resultado == {"tenants_odoo": 1}
        mock_delay.assert_called_once_with(str(empresa_a.id_empresa))


# ── Comando: configurar_conector_odoo ────────────────────────────────────────


class TestConfigurarConectorOdoo:
    def test_crea_instancia_con_credenciales_cifradas(self, empresa_a):
        out = StringIO()
        call_command(
            "configurar_conector_odoo",
            "--empresa",
            str(empresa_a.id_empresa),
            "--host",
            "https://lubrikca.odoo.com",
            "--db",
            "lubrikca",
            "--user",
            "api@lubrikca.com",
            "--api-key",
            "secreto-123",
            "--nombre",
            "Odoo Lubrikca",
            "--entidades",
            "pagos,contactos",
            "--intervalo",
            "60",
            stdout=out,
        )
        inst = ConectorInstancia.objects.get(
            id_empresa=empresa_a, nombre="Odoo Lubrikca"
        )
        cfg = inst.get_config()
        assert cfg["host"] == "https://lubrikca.odoo.com"
        assert cfg["api_key"] == "secreto-123"
        assert inst.entidades_activas == ["pagos", "contactos"]
        assert inst.intervalo_sync_minutos == 60
        assert inst.id_proveedor.codigo == "odoo"
        # La salida NUNCA debe filtrar la api_key (R-CODE-8).
        assert "secreto-123" not in out.getvalue()

    def test_datasource_odoo_fija_parametro(self, empresa_a):
        from apps.configuracion_motor.models import ParametroSistema

        call_command(
            "configurar_conector_odoo",
            "--empresa",
            str(empresa_a.id_empresa),
            "--host",
            "https://x.odoo.com",
            "--user",
            "u",
            "--api-key",
            "k",
            "--datasource-odoo",
            stdout=StringIO(),
        )
        param = ParametroSistema.objects.get(
            id_empresa=empresa_a, codigo_parametro="cxc.datasource"
        )
        assert param.valor_parametro == "odoo"
        assert param.activo is True

    def test_falla_sin_credenciales(self, empresa_a):
        with pytest.raises(CommandError):
            call_command(
                "configurar_conector_odoo",
                "--empresa",
                str(empresa_a.id_empresa),
                stdout=StringIO(),
            )

    def test_update_idempotente(self, empresa_a):
        """Re-ejecutar actualiza la misma instancia (unique empresa+nombre)."""
        args = [
            "--empresa",
            str(empresa_a.id_empresa),
            "--host",
            "https://x.odoo.com",
            "--user",
            "u",
            "--api-key",
            "k",
            "--nombre",
            "Odoo Lubrikca",
        ]
        call_command("configurar_conector_odoo", *args, stdout=StringIO())
        call_command(
            "configurar_conector_odoo", *args, "--intervalo", "30", stdout=StringIO()
        )
        insts = ConectorInstancia.objects.filter(
            id_empresa=empresa_a, nombre="Odoo Lubrikca"
        )
        assert insts.count() == 1
        assert insts.first().intervalo_sync_minutos == 30

    def test_test_connection_actualiza_estado(self, empresa_a):
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=True,
            message="Conexión exitosa con Odoo 17.0",
            version="17.0",
        )
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            call_command(
                "configurar_conector_odoo",
                "--empresa",
                str(empresa_a.id_empresa),
                "--host",
                "https://x.odoo.com",
                "--user",
                "u",
                "--api-key",
                "k",
                "--test",
                stdout=StringIO(),
            )
        inst = ConectorInstancia.objects.get(id_empresa=empresa_a)
        assert inst.estado == "activo"
        assert inst.version_detectada == "17.0"

    def test_resuelve_empresa_por_rif(self, empresa_a):
        """--empresa acepta el RIF (no solo el UUID): rama de fallback."""
        call_command(
            "configurar_conector_odoo",
            "--empresa",
            empresa_a.identificador_fiscal,
            "--host",
            "https://x.odoo.com",
            "--user",
            "u",
            "--api-key",
            "k",
            stdout=StringIO(),
        )
        assert ConectorInstancia.objects.filter(id_empresa=empresa_a).exists()

    def test_falla_empresa_inexistente(self):
        """RIF que no corresponde a ninguna empresa → CommandError."""
        with pytest.raises(CommandError):
            call_command(
                "configurar_conector_odoo",
                "--empresa",
                "J-00000000-0",
                "--host",
                "https://x.odoo.com",
                "--user",
                "u",
                "--api-key",
                "k",
                stdout=StringIO(),
            )

    def test_test_connection_falla_marca_error(self, empresa_a):
        """Con --test y conexión fallida, la instancia queda en estado 'error'."""
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=False, message="auth error"
        )
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            call_command(
                "configurar_conector_odoo",
                "--empresa",
                str(empresa_a.id_empresa),
                "--host",
                "https://x.odoo.com",
                "--user",
                "u",
                "--api-key",
                "k",
                "--test",
                stdout=StringIO(),
            )
        inst = ConectorInstancia.objects.get(id_empresa=empresa_a)
        assert inst.estado == "error"
        assert inst.mensaje_estado == "auth error"


# ── Comando: validar_conector_odoo ───────────────────────────────────────────


class TestValidarConectorOdoo:
    def _crear_instancia(self, empresa):
        call_command(
            "configurar_conector_odoo",
            "--empresa",
            str(empresa.id_empresa),
            "--host",
            "https://x.odoo.com",
            "--user",
            "u",
            "--api-key",
            "k",
            "--nombre",
            "Odoo Lubrikca",
            stdout=StringIO(),
        )

    def test_valida_conexion_y_muestra_cartera(self, empresa_a):
        self._crear_instancia(empresa_a)
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=True,
            message="Conexión exitosa con Odoo 17.0",
            version="17.0",
        )
        fake.pull_cartera_vencida.return_value = [
            {
                "cliente_nombre": "Cliente A",
                "monto_pendiente": "100.00",
                "bucket": "31_60",
                "orden_ref": "INV/1",
            },
        ]
        out = StringIO()
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            call_command(
                "validar_conector_odoo",
                "--empresa",
                str(empresa_a.id_empresa),
                stdout=out,
            )
        salida = out.getvalue()
        assert "Conexión OK" in salida
        assert "1 partidas" in salida
        assert "Cliente A" in salida

    def test_falla_si_conexion_falla(self, empresa_a):
        self._crear_instancia(empresa_a)
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=False, message="auth error"
        )
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            with pytest.raises(CommandError):
                call_command(
                    "validar_conector_odoo",
                    "--empresa",
                    str(empresa_a.id_empresa),
                    stdout=StringIO(),
                )

    def test_falla_sin_conector_configurado(self, empresa_a):
        with pytest.raises(CommandError):
            call_command(
                "validar_conector_odoo",
                "--empresa",
                str(empresa_a.id_empresa),
                stdout=StringIO(),
            )

    def test_resuelve_por_instancia_y_cartera_vacia(self, empresa_a):
        """--instancia <id> resuelve directo; cartera vacía → warning informativo."""
        self._crear_instancia(empresa_a)
        inst = ConectorInstancia.objects.get(id_empresa=empresa_a)
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=True, message="ok", version="17.0"
        )
        fake.pull_cartera_vencida.return_value = []
        out = StringIO()
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            call_command(
                "validar_conector_odoo", "--instancia", str(inst.pk), stdout=out
            )
        assert "Sin cartera vencida" in out.getvalue()

    def test_instancia_inexistente(self):
        with pytest.raises(CommandError):
            call_command(
                "validar_conector_odoo",
                "--instancia",
                "00000000-0000-0000-0000-000000000000",
                stdout=StringIO(),
            )

    def test_sin_empresa_ni_instancia(self):
        with pytest.raises(CommandError):
            call_command("validar_conector_odoo", stdout=StringIO())

    def test_resuelve_empresa_por_rif(self, empresa_a):
        self._crear_instancia(empresa_a)
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=True, message="ok", version="17.0"
        )
        fake.pull_cartera_vencida.return_value = []
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            call_command(
                "validar_conector_odoo",
                "--empresa",
                empresa_a.identificador_fiscal,
                stdout=StringIO(),
            )

    def test_empresa_rif_inexistente(self):
        with pytest.raises(CommandError):
            call_command(
                "validar_conector_odoo", "--empresa", "J-99999999-9", stdout=StringIO()
            )

    def test_pull_cartera_falla(self, empresa_a):
        """Si pull_cartera_vencida lanza, el comando aborta con CommandError."""
        self._crear_instancia(empresa_a)
        fake = MagicMock()
        fake.test_connection.return_value = ConnResult(
            success=True, message="ok", version="17.0"
        )
        fake.pull_cartera_vencida.side_effect = RuntimeError("boom")
        with patch(
            "apps.integration_hub.connectors.registry.registry.get_connector",
            return_value=fake,
        ):
            with pytest.raises(CommandError):
                call_command(
                    "validar_conector_odoo",
                    "--empresa",
                    str(empresa_a.id_empresa),
                    stdout=StringIO(),
                )

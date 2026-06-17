"""
1.G — Comisiones de vendedores: superficie API + aislamiento R-CODE-1.

Cubre:
  - CRUD de esquemas de comisión (empresa inyectada, validaciones 400,
    FK de vendedor/categoría ajenos rechazados, objetos ajenos → 404).
  - Overrides por categoría (coherencia esquema↔categoría misma empresa).
  - Listado/consulta de comisiones (solo lectura, filtros, aislamiento).
  - /comisiones/resumen/ (montos como string — R-CODE-4).
  - /comisiones/liquidar/ (idempotencia con Idempotency-Key, scoping).
  - PATCH NotaVenta → ANULADA anula la comisión en la misma transacción;
    con comisión LIQUIDADA la anulación se rechaza y nada cambia.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ventas.models import ComisionVenta, EsquemaComision, NotaVenta

pytestmark = [pytest.mark.django_db]

BASE_ESQUEMAS = "/api/ventas/esquemas-comision/"
BASE_OVERRIDES = "/api/ventas/esquemas-comision-categorias/"
BASE_COMISIONES = "/api/ventas/comisiones/"


# ── Helpers de escenario ──────────────────────────────────────────────────────

_SEQ = iter(range(1, 10_000))


def _vendedor(empresa, username=None):
    from tests.factories import UsuariosFactory

    return UsuariosFactory(username=username or f"vend_{next(_SEQ)}", empresa=empresa)


def _cliente(empresa):
    from apps.crm.models import Cliente

    n = next(_SEQ)
    return Cliente.objects.create(
        id_empresa=empresa, razon_social=f"Cliente API {n}", rif=f"J-88{n:06d}-0"
    )


def _categoria(empresa, nombre=None):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(
        id_empresa=empresa, nombre_categoria=nombre or f"Cat API {next(_SEQ)}"
    )


def _esquema(empresa, vendedor, porcentaje="5.0000"):
    return EsquemaComision.objects.create(
        id_empresa=empresa, vendedor=vendedor, porcentaje_base=Decimal(porcentaje)
    )


def _comision(empresa, vendedor, monto="10.0000", fecha=None, estado="DEVENGADA", esquema=None):
    """Comisión persistida directo (la mecánica de devengo se prueba en integration)."""
    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=_cliente(empresa),
        id_vendedor=vendedor,
        numero_nota=f"NV-API-{next(_SEQ):04d}",
        fecha_nota=fecha or timezone.localdate(),
        estado="ENTREGADA",
    )
    return ComisionVenta.objects.create(
        id_empresa=empresa,
        vendedor=vendedor,
        nota_venta=nota,
        esquema=esquema or _esquema(empresa, vendedor),
        base_comisionable=Decimal(monto) * 20,
        monto=Decimal(monto),
        estado=estado,
        fecha_devengo=fecha or timezone.localdate(),
    )


def _resultados(data):
    return data["results"] if isinstance(data, dict) and "results" in data else data


# ── Esquemas: CRUD + validaciones ─────────────────────────────────────────────


def test_crear_esquema_inyecta_empresa_del_usuario(client_a, empresa_a, empresa_b):
    vendedor = _vendedor(empresa_a)
    resp = client_a.post(
        BASE_ESQUEMAS,
        {
            "vendedor": str(vendedor.pk),
            "porcentaje_base": "5.0000",
            # H-API-1: aunque el cliente intente fijar otra empresa, se ignora.
            "id_empresa": str(empresa_b.id_empresa),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    esquema = EsquemaComision.objects.get(pk=resp.data["id_esquema_comision"])
    assert esquema.id_empresa == empresa_a


@pytest.mark.parametrize("porcentaje", ["-1", "100.0001"])
def test_porcentaje_fuera_de_rango_400(client_a, empresa_a, porcentaje):
    vendedor = _vendedor(empresa_a)
    resp = client_a.post(
        BASE_ESQUEMAS,
        {"vendedor": str(vendedor.pk), "porcentaje_base": porcentaje},
        format="json",
    )
    assert resp.status_code == 400
    assert "porcentaje_base" in resp.data


def test_vigencia_invertida_400(client_a, empresa_a):
    vendedor = _vendedor(empresa_a)
    resp = client_a.post(
        BASE_ESQUEMAS,
        {
            "vendedor": str(vendedor.pk),
            "porcentaje_base": "5.0000",
            "vigente_desde": "2026-06-30",
            "vigente_hasta": "2026-06-01",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "vigente_hasta" in resp.data


def test_vendedor_de_otra_empresa_400(client_a, empresa_b):
    """SEC-M1: el FK vendedor está acotado a usuarios de empresas visibles."""
    vendedor_b = _vendedor(empresa_b)
    resp = client_a.post(
        BASE_ESQUEMAS,
        {"vendedor": str(vendedor_b.pk), "porcentaje_base": "5.0000"},
        format="json",
    )
    assert resp.status_code == 400
    assert "vendedor" in resp.data


def test_esquemas_aislados_entre_empresas(client_a, empresa_a, empresa_b):
    """R-CODE-1: list no filtra, detail/patch/delete ajenos → 404."""
    propio = _esquema(empresa_a, _vendedor(empresa_a))
    ajeno = _esquema(empresa_b, _vendedor(empresa_b))

    resp = client_a.get(BASE_ESQUEMAS)
    ids = {r["id_esquema_comision"] for r in _resultados(resp.data)}
    assert str(propio.pk) in ids
    assert str(ajeno.pk) not in ids

    assert client_a.get(f"{BASE_ESQUEMAS}{ajeno.pk}/").status_code == 404
    assert (
        client_a.patch(
            f"{BASE_ESQUEMAS}{ajeno.pk}/", {"porcentaje_base": "1.0000"}, format="json"
        ).status_code
        == 404
    )
    assert client_a.delete(f"{BASE_ESQUEMAS}{ajeno.pk}/").status_code == 404
    ajeno.refresh_from_db()
    assert ajeno.porcentaje_base == Decimal("5.0000")


# ── Overrides por categoría ───────────────────────────────────────────────────


def test_override_crear_y_validar_rango(client_a, empresa_a):
    esquema = _esquema(empresa_a, _vendedor(empresa_a))
    categoria = _categoria(empresa_a)

    ok = client_a.post(
        BASE_OVERRIDES,
        {"esquema": str(esquema.pk), "categoria": str(categoria.pk), "porcentaje": "10.0000"},
        format="json",
    )
    assert ok.status_code == 201, ok.data

    malo = client_a.post(
        BASE_OVERRIDES,
        {"esquema": str(esquema.pk), "categoria": str(categoria.pk), "porcentaje": "101"},
        format="json",
    )
    assert malo.status_code == 400
    assert "porcentaje" in malo.data


def test_override_categoria_ajena_400(client_a, empresa_a, empresa_b):
    esquema = _esquema(empresa_a, _vendedor(empresa_a))
    categoria_b = _categoria(empresa_b)
    resp = client_a.post(
        BASE_OVERRIDES,
        {"esquema": str(esquema.pk), "categoria": str(categoria_b.pk), "porcentaje": "10.0000"},
        format="json",
    )
    assert resp.status_code == 400
    assert "categoria" in resp.data


def test_override_cruce_entre_empresas_visibles_400(empresa_a, empresa_b):
    """
    Usuario con DOS empresas visibles: ambos FKs pasan el scope de visibilidad,
    pero el serializer exige que esquema y categoría sean de la MISMA empresa.
    """
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user_ab = UsuariosFactory(username="user_dos_empresas", empresas=[empresa_a, empresa_b])
    client = APIClient()
    client.force_authenticate(user=user_ab)

    esquema_a = _esquema(empresa_a, _vendedor(empresa_a))
    categoria_b = _categoria(empresa_b)
    resp = client.post(
        BASE_OVERRIDES,
        {"esquema": str(esquema_a.pk), "categoria": str(categoria_b.pk), "porcentaje": "10.0000"},
        format="json",
    )
    assert resp.status_code == 400
    assert "misma empresa" in str(resp.data["categoria"])


def test_overrides_aislados(client_a, empresa_a, empresa_b):
    from apps.ventas.models import EsquemaComisionCategoria

    ajeno = EsquemaComisionCategoria.objects.create(
        esquema=_esquema(empresa_b, _vendedor(empresa_b)),
        categoria=_categoria(empresa_b),
        porcentaje=Decimal("9.0000"),
    )
    resp = client_a.get(BASE_OVERRIDES)
    assert str(ajeno.pk) not in {
        r["id_esquema_comision_categoria"] for r in _resultados(resp.data)
    }
    assert client_a.get(f"{BASE_OVERRIDES}{ajeno.pk}/").status_code == 404


# ── Comisiones: solo lectura + filtros + aislamiento ──────────────────────────


def test_comisiones_listado_aislado_y_solo_lectura(client_a, empresa_a, empresa_b):
    propia = _comision(empresa_a, _vendedor(empresa_a))
    ajena = _comision(empresa_b, _vendedor(empresa_b))

    resp = client_a.get(BASE_COMISIONES)
    assert resp.status_code == 200
    ids = {r["id_comision_venta"] for r in _resultados(resp.data)}
    assert str(propia.pk) in ids
    assert str(ajena.pk) not in ids
    # Montos como string (R-CODE-4)
    fila = next(r for r in _resultados(resp.data) if r["id_comision_venta"] == str(propia.pk))
    assert fila["monto"] == "10.0000"

    assert client_a.get(f"{BASE_COMISIONES}{ajena.pk}/").status_code == 404
    # ReadOnly: no hay escritura directa
    assert client_a.post(BASE_COMISIONES, {}, format="json").status_code == 405
    assert (
        client_a.patch(f"{BASE_COMISIONES}{propia.pk}/", {"estado": "LIQUIDADA"}, format="json").status_code
        == 405
    )
    assert client_a.delete(f"{BASE_COMISIONES}{propia.pk}/").status_code == 405


def test_comisiones_filtros(client_a, empresa_a):
    hoy = timezone.localdate()
    v1 = _vendedor(empresa_a)
    v2 = _vendedor(empresa_a)
    de_v1 = _comision(empresa_a, v1, fecha=hoy)
    vieja_v1 = _comision(empresa_a, v1, fecha=hoy - timedelta(days=90))
    liquidada_v2 = _comision(empresa_a, v2, estado="LIQUIDADA")

    por_vendedor = client_a.get(BASE_COMISIONES, {"vendedor": str(v1.pk)})
    assert {r["id_comision_venta"] for r in _resultados(por_vendedor.data)} == {
        str(de_v1.pk),
        str(vieja_v1.pk),
    }

    por_estado = client_a.get(BASE_COMISIONES, {"estado": "liquidada"})
    assert {r["id_comision_venta"] for r in _resultados(por_estado.data)} == {str(liquidada_v2.pk)}

    por_fecha = client_a.get(
        BASE_COMISIONES,
        {"desde": str(hoy - timedelta(days=30)), "hasta": str(hoy)},
    )
    ids = {r["id_comision_venta"] for r in _resultados(por_fecha.data)}
    assert str(vieja_v1.pk) not in ids
    assert {str(de_v1.pk), str(liquidada_v2.pk)} <= ids


def test_comisiones_filtros_invalidos_400(client_a):
    assert client_a.get(BASE_COMISIONES, {"desde": "no-fecha"}).status_code == 400
    assert client_a.get(BASE_COMISIONES, {"vendedor": "no-uuid"}).status_code == 400


def test_resumen_por_vendedor(client_a, empresa_a, empresa_b):
    vendedor = _vendedor(empresa_a, "vend_resumen")
    esquema = _esquema(empresa_a, vendedor)
    _comision(empresa_a, vendedor, monto="10.0000", esquema=esquema)
    _comision(empresa_a, vendedor, monto="2.5000", esquema=esquema)
    _comision(empresa_a, vendedor, monto="7.0000", estado="LIQUIDADA", esquema=esquema)
    _comision(empresa_b, _vendedor(empresa_b), monto="99.0000")  # no debe aparecer

    resp = client_a.get(f"{BASE_COMISIONES}resumen/")
    assert resp.status_code == 200
    filas = resp.data["resultados"]
    assert len(filas) == 1
    fila = filas[0]
    assert fila["vendedor"] == str(vendedor.pk)
    assert fila["vendedor_username"] == "vend_resumen"
    assert fila["devengada"] == "12.5000"
    assert fila["liquidada"] == "7.0000"
    assert fila["anulada"] == "0"
    assert fila["cantidad"] == 3


# ── Liquidar ──────────────────────────────────────────────────────────────────


def test_liquidar_marca_y_es_idempotente_con_clave(client_a, empresa_a, user_a):
    hoy = timezone.localdate()
    vendedor = _vendedor(empresa_a)
    esquema = _esquema(empresa_a, vendedor)
    c1 = _comision(empresa_a, vendedor, monto="5.0000", esquema=esquema)
    c2 = _comision(empresa_a, vendedor, monto="3.2500", esquema=esquema)

    payload = {
        "vendedor": str(vendedor.pk),
        "desde": str(hoy - timedelta(days=7)),
        "hasta": str(hoy),
    }
    resp = client_a.post(
        f"{BASE_COMISIONES}liquidar/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="liq-test-001",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["liquidadas"] == 2
    assert resp.data["monto_total"] == "8.2500"
    for c in (c1, c2):
        c.refresh_from_db()
        assert c.estado == "LIQUIDADA"
        assert c.fecha_liquidacion == hoy
        assert c.liquidada_por == user_a

    # Reintento con la MISMA clave: reproduce la respuesta sin re-ejecutar —
    # la comisión nueva creada entre medio NO se liquida.
    nueva = _comision(empresa_a, vendedor, monto="4.0000", esquema=esquema)
    replay = client_a.post(
        f"{BASE_COMISIONES}liquidar/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="liq-test-001",
    )
    assert replay.status_code == 200
    assert replay.data["liquidadas"] == 2
    nueva.refresh_from_db()
    assert nueva.estado == "DEVENGADA"


def test_liquidar_vendedor_ajeno_400(client_a, empresa_b):
    vendedor_b = _vendedor(empresa_b)
    _comision(empresa_b, vendedor_b)
    resp = client_a.post(
        f"{BASE_COMISIONES}liquidar/",
        {
            "vendedor": str(vendedor_b.pk),
            "desde": str(timezone.localdate() - timedelta(days=7)),
            "hasta": str(timezone.localdate()),
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "vendedor" in resp.data
    assert ComisionVenta.objects.filter(estado="LIQUIDADA").count() == 0


def test_liquidar_validaciones_400(client_a, empresa_a):
    vendedor = _vendedor(empresa_a)
    hoy = timezone.localdate()
    # rango invertido
    resp = client_a.post(
        f"{BASE_COMISIONES}liquidar/",
        {"vendedor": str(vendedor.pk), "desde": str(hoy), "hasta": str(hoy - timedelta(days=1))},
        format="json",
    )
    assert resp.status_code == 400
    # body incompleto
    assert (
        client_a.post(f"{BASE_COMISIONES}liquidar/", {"vendedor": str(vendedor.pk)}, format="json").status_code
        == 400
    )


# ── Anulación de la venta vía API ─────────────────────────────────────────────


def test_patch_nota_anulada_anula_comision(client_a, empresa_a):
    comision = _comision(empresa_a, _vendedor(empresa_a))
    nota = comision.nota_venta

    resp = client_a.patch(
        f"/api/ventas/notas-venta/{nota.pk}/", {"estado": "ANULADA"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    comision.refresh_from_db()
    assert comision.estado == "ANULADA"


def test_patch_nota_anulada_con_comision_liquidada_400_y_rollback(client_a, empresa_a):
    """Misma transacción: si la comisión no puede anularse, la nota NO queda anulada."""
    comision = _comision(empresa_a, _vendedor(empresa_a), estado="LIQUIDADA")
    nota = comision.nota_venta

    resp = client_a.patch(
        f"/api/ventas/notas-venta/{nota.pk}/", {"estado": "ANULADA"}, format="json"
    )
    assert resp.status_code == 400
    assert "liquidada" in str(resp.data).lower()
    nota.refresh_from_db()
    comision.refresh_from_db()
    assert nota.estado == "ENTREGADA"  # rollback de la transacción
    assert comision.estado == "LIQUIDADA"


def test_patch_nota_otro_campo_no_toca_comision(client_a, empresa_a):
    """Editar la nota sin anularla no altera la comisión."""
    comision = _comision(empresa_a, _vendedor(empresa_a))
    nota = comision.nota_venta

    resp = client_a.patch(
        f"/api/ventas/notas-venta/{nota.pk}/", {"observaciones": "ajuste"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    comision.refresh_from_db()
    assert comision.estado == "DEVENGADA"


# ── Entrega vía API (flujo end-to-end del devengo) ────────────────────────────


def _nota_borrador_con_stock(empresa, usuario, vendedor):
    """Nota BORRADOR de 3 × 20.00 con stock disponible en un almacén nuevo."""
    from apps.almacenes.models import Almacen
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
    from apps.inventario.services import registrar_movimiento
    from apps.ventas.models import DetalleNotaVenta

    n = next(_SEQ)
    almacen = Almacen.objects.create(
        id_empresa=empresa, nombre_almacen=f"Almacén E2E {n}", codigo_almacen=f"ALM-E2E-{n}"
    )
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa, nombre="Unidad", abreviatura=f"UN-{n}", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa, nombre_categoria=f"Cat E2E {n}"
    )
    producto = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=f"Producto E2E {n}",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=empresa.id_moneda_base,
        precio_venta_sugerido=Decimal("20.00"),
    )
    registrar_movimiento(
        empresa=empresa,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal("100"),
        almacen_destino=almacen,
        usuario=usuario,
    )
    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=_cliente(empresa),
        id_vendedor=vendedor,
        numero_nota=f"NV-E2E-{n:04d}",
        fecha_nota=timezone.localdate(),
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto,
        cantidad=Decimal("3"),
        precio_unitario=Decimal("20.00"),
        subtotal=Decimal("60.00"),
    )
    return nota, almacen


def test_entregar_por_api_devenga_comision(client_a, empresa_a, user_a):
    vendedor = _vendedor(empresa_a)
    _esquema(empresa_a, vendedor, porcentaje="5.0000")
    nota, almacen = _nota_borrador_con_stock(empresa_a, user_a, vendedor)

    resp = client_a.post(
        f"/api/ventas/notas-venta/{nota.pk}/entregar/",
        {"almacen_id": str(almacen.pk)},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["estado"] == "ENTREGADA"
    assert resp.data["comision_devengada"] is True
    assert resp.data["comision_monto"] == "3.0000"  # 60.00 × 5%

    comision = ComisionVenta.objects.get(nota_venta=nota)
    assert comision.estado == "DEVENGADA"
    listado = client_a.get(BASE_COMISIONES, {"vendedor": str(vendedor.pk)})
    assert {r["id_comision_venta"] for r in _resultados(listado.data)} == {str(comision.pk)}


def test_entregar_validaciones(client_a, client_b, empresa_a, empresa_b, user_a):
    vendedor = _vendedor(empresa_a)
    nota, almacen = _nota_borrador_con_stock(empresa_a, user_a, vendedor)

    # Sin almacén → 400
    sin_almacen = client_a.post(f"/api/ventas/notas-venta/{nota.pk}/entregar/", {}, format="json")
    assert sin_almacen.status_code == 400
    assert "almacen_id" in sin_almacen.data

    # Almacén de otra empresa → 400 (no se filtra su existencia)
    from apps.almacenes.models import Almacen

    almacen_b = Almacen.objects.create(
        id_empresa=empresa_b, nombre_almacen="Almacén B", codigo_almacen="ALM-B-E2E"
    )
    cruzado = client_a.post(
        f"/api/ventas/notas-venta/{nota.pk}/entregar/",
        {"almacen_id": str(almacen_b.pk)},
        format="json",
    )
    assert cruzado.status_code == 400

    # Nota ajena → 404 (R-CODE-1)
    ajeno = client_b.post(
        f"/api/ventas/notas-venta/{nota.pk}/entregar/",
        {"almacen_id": str(almacen.pk)},
        format="json",
    )
    assert ajeno.status_code == 404

    # Entrega válida y reintento sobre nota ya ENTREGADA → 400 controlado
    ok = client_a.post(
        f"/api/ventas/notas-venta/{nota.pk}/entregar/",
        {"almacen_id": str(almacen.pk)},
        format="json",
    )
    assert ok.status_code == 200
    repetida = client_a.post(
        f"/api/ventas/notas-venta/{nota.pk}/entregar/",
        {"almacen_id": str(almacen.pk)},
        format="json",
    )
    assert repetida.status_code == 400
    assert ComisionVenta.objects.filter(nota_venta=nota).count() <= 1

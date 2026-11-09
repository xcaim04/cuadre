"""Cada regla de silver con archivos chiquitos hechos a mano, y las mismas reglas sobre los datos generados."""

import json
from decimal import Decimal

from pipeline import ejecutar

PEDIDOS = "id_pedido,actualizado_en,id_mensajero,cliente,direccion,importe\n"
P1 = PEDIDOS + "P1,2026-09-01 10:00:00,M01,Ana López,Calle 1 #1,100.00\n"
LIQUIDACIONES = "fecha,mensajero,importe\n"


def evento(id_evento, tipo="entrega", cuando="2026-09-01 15:00:00", importe="100.00", pedido="P1", mensajero="M01"):
    return json.dumps({"id_evento": id_evento, "id_pedido": pedido, "id_mensajero": mensajero, "tipo": tipo,
                       "ocurrido_en": cuando, "importe": importe})


def correr(tmp_path, eventos: dict[str, list[str]], pedidos=P1, liquidaciones=LIQUIDACIONES):
    """eventos: día del archivo -> líneas."""
    (tmp_path / "pedidos").mkdir()
    (tmp_path / "pedidos" / "2026-09-01.csv").write_text(pedidos, encoding="utf-8")
    (tmp_path / "eventos").mkdir()
    for dia, lineas in eventos.items():
        (tmp_path / "eventos" / f"{dia}.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    (tmp_path / "liquidaciones.csv").write_text(liquidaciones, encoding="utf-8")
    (tmp_path / "extracto_banco.csv").write_text("fecha,referencia,importe\n")
    return ejecutar(tmp_path)


def uno(con, sql):
    return con.execute(sql).fetchone()[0]


def test_evento_repetido_cuenta_una_vez(tmp_path):
    con = correr(tmp_path, {"2026-09-01": [evento("E1")], "2026-09-02": [evento("E1")]})
    assert uno(con, "SELECT count(*) FROM silver.eventos") == 1
    assert uno(con, "SELECT _archivo_origen FROM silver.eventos") == "2026-09-01.jsonl"


def test_estado_sale_del_evento_mas_reciente_no_del_ultimo_que_llego(tmp_path):
    con = correr(tmp_path, {
        "2026-09-03": [evento("E2", "devolucion", "2026-09-03 10:00:00")],
        "2026-09-04": [evento("E1", "entrega", "2026-09-01 15:00:00")],  # la entrega llega tarde
    })
    assert uno(con, "SELECT estado FROM silver.pedidos WHERE id_pedido = 'P1'") == "devuelto"
    assert uno(con, "SELECT count(*) FROM silver.cuarentena") == 0


def test_importe_cobrable_es_el_vigente_al_entregar(tmp_path):
    pedidos = P1 + "P1,2026-09-01 18:00:00,M01,Ana López,Calle 1 #1,150.00\n"  # edición después de entregar
    con = correr(tmp_path, {"2026-09-01": [evento("E1")]}, pedidos=pedidos)
    assert con.execute("SELECT importe_actual, importe_cobrado, importe_cobrable FROM silver.pedidos").fetchone() == (
        Decimal("150.00"), Decimal("100.00"), Decimal("100.00"))
    assert con.execute("SELECT importe, CAST(valido_hasta AS VARCHAR) FROM silver.pedidos_historial ORDER BY valido_desde").fetchall() == [
        (Decimal("100.00"), "2026-09-01 18:00:00"), (Decimal("150.00"), None)]


def test_alias_de_mensajero_se_normaliza_y_lo_desconocido_va_a_cuarentena(tmp_path):
    liquidaciones = LIQUIDACIONES + "2026-09-01,  YOANDRY   PÉREZ ,50.00\n2026-09-01,Yoyi,30.00\n2026-09-01,Fulano,20.00\n"
    con = correr(tmp_path, {"2026-09-01": [evento("E1")]}, liquidaciones=liquidaciones)
    assert con.execute("SELECT id_mensajero, sum(importe) FROM silver.liquidaciones GROUP BY ALL").fetchall() == [
        ("M01", Decimal("80.00"))]
    assert con.execute("SELECT referencia, motivo FROM silver.cuarentena").fetchall() == [("Fulano", "mensajero_desconocido")]


def test_lo_que_no_se_puede_usar_va_a_cuarentena_con_su_motivo(tmp_path):
    pedidos = P1 + "P2,2026-09-01 10:00:00,M02,Raúl,Calle 2 #2,80.00\n"
    con = correr(tmp_path, {"2026-09-01": [
        evento("E1", importe=None),                              # la app marcó entregado sin cobro
        evento("E2", "devolucion", "2026-09-02 10:00:00", pedido="P2", mensajero="M02"),
        evento("E3", pedido="P99"),
        evento("E4", "recogida"),
        evento("E5", cuando="ayer"),
        evento("E6", mensajero="M99"),
        evento("E7", importe="0.00"),
    ]}, pedidos=pedidos)
    assert uno(con, "SELECT count(*) FROM silver.eventos") == 0
    assert dict(con.execute("SELECT referencia, motivo FROM silver.cuarentena").fetchall()) == {
        "E1": "entrega_sin_cobro", "E2": "devolucion_sin_entrega", "E3": "pedido_desconocido",
        "E4": "tipo_desconocido", "E5": "dato_invalido", "E6": "mensajero_desconocido", "E7": "importe_no_positivo",
    }
    assert uno(con, "SELECT list(DISTINCT estado) FROM silver.pedidos") == ["pendiente"]


def test_reglas_sobre_los_datos_generados(raw):
    con = ejecutar(raw)
    assert uno(con, "SELECT count(*) - count(DISTINCT id_evento) FROM silver.eventos") == 0
    # Cada entrega se cobró por la versión vigente, aunque haya pedidos editados después de entregar.
    assert uno(con, "SELECT count(*) FROM silver.pedidos WHERE estado <> 'pendiente' AND entregado_en IS NOT NULL "
                    "AND importe_cobrable IS DISTINCT FROM importe_cobrado") == 0
    assert uno(con, "SELECT count(*) FROM silver.pedidos WHERE importe_actual <> importe_cobrado") > 0
    assert con.execute("SELECT DISTINCT origen, motivo FROM silver.cuarentena").fetchall() == [("eventos", "entrega_sin_cobro")]

    # Adelanto del número piloto: con silver ya cuadra la deuda final de verdad.json.
    deuda = dict(con.execute("""
        SELECT id_mensajero, sum(importe) FROM (
            SELECT id_mensajero, CASE tipo WHEN 'entrega' THEN importe WHEN 'devolucion' THEN -importe ELSE 0 END AS importe
            FROM silver.eventos
            UNION ALL SELECT id_mensajero, -importe FROM silver.liquidaciones
        ) GROUP BY id_mensajero""").fetchall())
    verdad = json.loads((raw / "verdad.json").read_text())["deuda_al_cierre"]
    ultimo = max(v["fecha"] for v in verdad)
    assert deuda == {v["id_mensajero"]: Decimal(v["deuda"]) for v in verdad if v["fecha"] == ultimo}

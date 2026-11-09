"""Gold: el número piloto cuadra con la verdad día a día, la antigüedad es FIFO y nada se publica si falla la calidad."""

import json
from decimal import Decimal

from fabricar import LIQUIDACIONES, PEDIDOS, correr, escribir, evento
from pipeline import ejecutar, publicar_si_pasa

TRES_PEDIDOS = PEDIDOS + "".join(f"P{n},2026-09-01 10:00:00,M01,Ana López,Calle 1 #1,{importe}\n"
                                 for n, importe in ((1, "100.00"), (2, "50.00"), (3, "80.00"), (4, "70.00")))


def test_deuda_igual_a_la_verdad_cada_dia(raw):
    """El número piloto: la deuda de cada mensajero al cierre de cada día, al centavo."""
    con = ejecutar(raw)
    gold = {(str(f), m): d for f, m, d in con.execute("SELECT fecha, id_mensajero, deuda FROM gold.deuda_mensajero_dia").fetchall()}
    verdad = json.loads((raw / "verdad.json").read_text())["deuda_al_cierre"]
    assert gold == {(v["fecha"], v["id_mensajero"]): Decimal(v["deuda"]) for v in verdad}


def test_con_los_datos_generados_pasa_la_calidad_y_se_publica(raw, tmp_path):
    con = ejecutar(raw)
    resultado = publicar_si_pasa(con, tmp_path)
    assert len(resultado) == 12 and not any(resultado.values()), resultado
    assert {p.stem for p in tmp_path.glob("*.parquet")} == {"deuda_mensajero_dia", "cierre_caja", "pedidos_perdidos"}
    # El mensajero atrasado del generador acumula deuda de más de 7 días.
    assert con.execute("SELECT max(deuda_mas_7) FROM gold.deuda_mensajero_dia WHERE id_mensajero = 'M05'").fetchone()[0] > 0


def test_antiguedad_paga_primero_lo_mas_viejo(tmp_path):
    con = correr(tmp_path, {"2026-09-01": [
        evento("E1", cuando="2026-09-01 15:00:00", importe="100.00", pedido="P1"),
        evento("E2", cuando="2026-09-05 15:00:00", importe="50.00", pedido="P2"),
        evento("E3", "rechazo", cuando="2026-09-09 15:00:00", importe=None, pedido="P3"),
    ]}, pedidos=TRES_PEDIDOS, liquidaciones=LIQUIDACIONES + "2026-09-06,Yoandry Pérez,120.00\n")
    tramos = {str(f): (d, a, b, c) for f, d, a, b, c in con.execute(
        "SELECT fecha, deuda, deuda_0_2, deuda_3_7, deuda_mas_7 FROM gold.deuda_mensajero_dia WHERE id_mensajero = 'M01'").fetchall()}
    D = Decimal
    assert tramos["2026-09-05"] == (D("150.00"), D("50.00"), D("100.00"), D("0"))  # el cobro del día 1 tiene 4 días
    assert tramos["2026-09-06"] == (D("30.00"), D("30.00"), D("0"), D("0"))        # los 120 pagan los 100 viejos primero
    assert tramos["2026-09-09"] == (D("30.00"), D("0"), D("30.00"), D("0"))        # lo que queda es del día 5


def test_si_falla_la_calidad_no_se_publica_nada(tmp_path):
    raw = escribir(tmp_path / "raw", {"2026-09-01": [
        evento("E1", importe="100.00"),
        evento("E2", "devolucion", cuando="2026-09-02 10:00:00", importe="150.00"),  # devuelve más de lo cobrado
    ]})
    publicado = tmp_path / "gold"
    publicado.mkdir()
    (publicado / "deuda_mensajero_dia.parquet").write_bytes(b"lo de ayer")
    resultado = publicar_si_pasa(ejecutar(raw), publicado)
    assert resultado["devolucion_no_supera_cobro"] == 1
    assert [p.name for p in publicado.iterdir()] == ["deuda_mensajero_dia.parquet"]
    assert (publicado / "deuda_mensajero_dia.parquet").read_bytes() == b"lo de ayer"


def test_pedido_sin_cerrar_mas_de_3_dias_es_perdido(tmp_path):
    pedidos = TRES_PEDIDOS + "P5,2026-09-05 10:00:00,M01,Ana López,Calle 1 #1,90.00\n"
    con = correr(tmp_path, {"2026-09-01": [
        evento("E1", pedido="P1"),
        evento("E2", importe=None, pedido="P2"),                                    # entrega sin cobro: sigue pendiente
        evento("E4", "rechazo", cuando="2026-09-06 12:00:00", importe=None, pedido="P4"),  # fija el corte en el día 6
    ]}, pedidos=pedidos)
    assert con.execute("SELECT id_pedido, dias_sin_cierre, motivo_cuarentena FROM gold.pedidos_perdidos ORDER BY 1").fetchall() == [
        ("P2", 5, "entrega_sin_cobro"), ("P3", 5, None)]  # P5 lleva solo 1 día

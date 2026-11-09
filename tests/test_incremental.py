"""Carga diaria: da lo mismo que la completa, repetir un día no cambia nada y los eventos tardíos se absorben o se apartan."""

import json
from datetime import date, timedelta

import duckdb
import pytest

from fabricar import P1, escribir, evento
from pipeline import VENTANA, ejecutar, validar


def foto(con) -> dict[str, list[str]]:
    """Todas las tablas con sus filas ordenadas, sin las columnas de hora de carga."""
    tablas = con.execute("SELECT DISTINCT schema_name, table_name FROM duckdb_tables() ORDER BY ALL").fetchall()
    resultado = {}
    for esquema, tabla in tablas:
        columnas = [c for (c,) in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE schema_name = ? AND table_name = ? ORDER BY column_index",
            [esquema, tabla]).fetchall() if c not in ("_cargado_en", "cargado_en")]
        filas = con.execute(f"SELECT {', '.join(columnas)} FROM {esquema}.{tabla}").fetchall()
        resultado[f"{esquema}.{tabla}"] = sorted(map(str, filas))
    return resultado


def cargar_dia_a_dia(raw, db, hasta):
    dia = date(2026, 9, 1)
    while dia <= hasta:
        ejecutar(raw, db, dia).close()
        dia += timedelta(days=1)


@pytest.fixture(scope="module")
def diaria(raw, tmp_path_factory):
    """Una base cargada día a día, incluidos los días en que solo llegan eventos tardíos."""
    db = tmp_path_factory.mktemp("diaria") / "ruta.duckdb"
    ultimo = max(date.fromisoformat(a.stem) for a in (raw / "eventos").glob("*.jsonl"))
    cargar_dia_a_dia(raw, db, ultimo)
    return db, ultimo


def test_carga_diaria_igual_a_carga_completa(raw, diaria):
    completa, dia_a_dia = foto(ejecutar(raw)), foto(duckdb.connect(str(diaria[0])))
    assert completa.keys() == dia_a_dia.keys()
    for tabla in completa:
        assert completa[tabla] == dia_a_dia[tabla], tabla


def test_repetir_un_dia_no_cambia_nada(raw, diaria):
    db, ultimo = diaria
    antes = foto(duckdb.connect(str(db)))
    ejecutar(raw, db, ultimo).close()
    assert foto(duckdb.connect(str(db))) == antes


def test_ponerse_al_dia_despues_de_una_pausa_da_lo_mismo(raw, diaria, tmp_path):
    """Diez días cargados, una pausa, y de golpe todo lo demás: los tardíos de los días ya cerrados también entran."""
    db = tmp_path / "ruta.duckdb"
    cargar_dia_a_dia(raw, db, date(2026, 9, 10))
    con = ejecutar(raw, db, diaria[1])
    assert foto(con) == foto(duckdb.connect(str(diaria[0])))


def test_un_archivo_que_cambia_despues_de_cargado_detiene_la_carga(tmp_path):
    raw = escribir(tmp_path / "raw", {"2026-09-01": [evento("E1")]})
    ejecutar(raw, tmp_path / "ruta.duckdb", date(2026, 9, 1)).close()
    (raw / "pedidos" / "2026-09-01.csv").write_text(P1.replace("100.00", "999.00"), encoding="utf-8")
    with pytest.raises(ValueError, match="cambió después de cargado"):
        ejecutar(raw, tmp_path / "ruta.duckdb", date(2026, 9, 2))


def deuda_del_dia_1(con):
    return con.execute("SELECT deuda FROM gold.deuda_mensajero_dia WHERE fecha = '2026-09-01' AND id_mensajero = 'M01'").fetchone()[0]


def test_evento_tardio_dentro_de_la_ventana_corrige_la_deuda_pasada(tmp_path):
    pedidos = P1 + "P2,2026-09-01 10:00:00,M01,Ana López,Calle 1 #1,50.00\n"
    raw = escribir(tmp_path / "raw", {
        "2026-09-01": [evento("E1")],
        "2026-09-04": [evento("E2", importe="50.00", pedido="P2")],  # ocurrió el día 1, llega 3 días tarde
    }, pedidos=pedidos)
    db = tmp_path / "ruta.duckdb"
    cargar_dia_a_dia(raw, db, date(2026, 9, 3))
    assert deuda_del_dia_1(duckdb.connect(str(db))) == 100
    con = ejecutar(raw, db, date(2026, 9, 4))
    assert deuda_del_dia_1(con) == 150


def test_evento_fuera_de_la_ventana_va_a_cuarentena(tmp_path):
    pedidos = P1 + "P2,2026-09-01 10:00:00,M01,Ana López,Calle 1 #1,50.00\n"
    raw = escribir(tmp_path / "raw", {
        "2026-09-01": [evento("E1")],
        "2026-09-08": [evento("E2", importe="50.00", pedido="P2")],  # ocurrió el día 1, llega 7 días tarde
    }, pedidos=pedidos)
    db = tmp_path / "ruta.duckdb"
    cargar_dia_a_dia(raw, db, date(2026, 9, 8))
    con = duckdb.connect(str(db))
    assert deuda_del_dia_1(con) == 100
    assert con.execute("SELECT referencia, motivo FROM silver.cuarentena").fetchall() == [("E2", "fuera_de_ventana")]


def test_el_generador_no_produce_eventos_fuera_de_ventana(raw):
    """Si el generador atrasara más que la ventana, la verdad y gold dejarían de cuadrar sin que fuera un error."""
    for archivo in (raw / "eventos").glob("*.jsonl"):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if validar(linea):
                continue  # líneas que no cumplen el contrato
            ocurrido = date.fromisoformat(json.loads(linea)["ocurrido_en"][:10])
            assert (date.fromisoformat(archivo.stem) - ocurrido).days <= VENTANA

"""La versión BigQuery (Dataform) compila, es SQL válido de BigQuery y da los mismos números que DuckDB,
tanto en una ejecución completa como en una incremental.

No hace falta cuenta de Google: se compila con la CLI de Dataform, se traduce a DuckDB con sqlglot
y se ejecuta sobre el mismo bronze que usa la versión local.
"""

import csv
import json
import re
import shutil
import subprocess
from datetime import date

import duckdb
import pytest
import sqlglot

import cargar_bigquery
from pipeline import RAIZ, ejecutar, validar

CLI = RAIZ / "dataform" / "node_modules" / ".bin" / "dataform"
GOLD = ("deuda_mensajero_dia", "cierre_caja", "pedidos_perdidos")


@pytest.fixture(scope="module")
def compilado():
    if not CLI.exists() or not shutil.which("node"):
        pytest.skip("Falta la CLI de Dataform: cd dataform && npm install")
    salida = subprocess.run([str(CLI), "compile", str(RAIZ / "dataform"), "--json"],
                            capture_output=True, text=True, check=True).stdout
    return json.loads(salida)


@pytest.fixture(scope="module")
def local(raw, tmp_path_factory):
    db = tmp_path_factory.mktemp("local") / "local.duckdb"
    ejecutar(raw, db).close()
    return db


def a_duckdb(consulta: str) -> str:
    # `proyecto.dataset.tabla` -> `dataset.tabla`: en DuckDB el dataset es el esquema.
    sql = sqlglot.transpile(re.sub(r"`[\w-]+\.(\w+\.\w+)`", r"`\1`", consulta), read="bigquery", write="duckdb")[0]
    # sqlglot no traduce NORMALIZE(x, NFD); quitarle las marcas después es lo mismo que strip_accents.
    return re.sub(r"NORMALIZE\(([^,()]+), NFD\)", r"strip_accents(\1)", sql)


def nombre(accion) -> str:
    return f'{accion["target"]["schema"]}.{accion["target"]["name"]}'


def bronze_hasta(con, local_db, hasta: date | None = None):
    """Copia el bronze local (hasta un día, o entero) y el seed de alias, como los dejaría cargar_bigquery.py."""
    con.execute(f"ATTACH IF NOT EXISTS '{local_db}' AS local (READ_ONLY)")
    for esquema in ("bronze", "silver", "gold"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {esquema}")
    filtro = f"WHERE CAST(left(_archivo_origen, 10) AS DATE) <= DATE '{hasta}'" if hasta else ""
    for tabla in ("pedidos", "eventos", "liquidaciones", "extracto_banco", "rechazos_contrato"):
        con.execute(f"CREATE OR REPLACE TABLE bronze.{tabla} AS SELECT * FROM local.bronze.{tabla} {filtro}")
    con.execute(f"CREATE OR REPLACE TABLE bronze.alias_mensajeros AS SELECT * FROM read_csv('{cargar_bigquery.ALIAS}', all_varchar = true)")


def en_orden(compilado):
    """Las tablas en un orden en que cada una se ejecuta cuando ya existen las que lee."""
    pendientes = {nombre(t): t for t in compilado["tables"]}
    while pendientes:
        listas = [n for n, t in pendientes.items()
                  if all(f'{d["schema"]}.{d["name"]}' not in pendientes for d in t.get("dependencyTargets", []))]
        assert listas, "dependencias circulares"
        for n in listas:
            yield n, pendientes.pop(n)


def ejecutar_dataform(con, compilado, incremental: bool):
    """Como `dataform run`: las incrementales hacen MERGE por uniqueKey con su consulta incremental; el resto se reconstruye."""
    for tabla, accion in en_orden(compilado):
        if not (incremental and accion["type"] == "incremental"):
            con.execute(f"CREATE OR REPLACE TABLE {tabla} AS {a_duckdb(accion['query'])}")
            continue
        con.execute(f"CREATE OR REPLACE TEMP TABLE nuevo AS {a_duckdb(accion['incrementalQuery'])}")
        iguales = " AND ".join(f"n.{k} = t.{k}" for k in accion["uniqueKey"])
        con.execute(f"DELETE FROM {tabla} t WHERE EXISTS (SELECT 1 FROM nuevo n WHERE {iguales})")
        con.execute(f"INSERT INTO {tabla} BY NAME FROM nuevo")


def mismos_numeros(con, compilado):
    for tabla in GOLD:
        assert con.execute(f"SELECT * FROM gold.{tabla} ORDER BY ALL").fetchall() == \
            con.execute(f"SELECT * FROM local.gold.{tabla} ORDER BY ALL").fetchall(), tabla
    for prueba in compilado["assertions"]:
        assert con.execute(a_duckdb(prueba["query"])).fetchall() == [], prueba["target"]["name"]


def test_compila_sin_errores_y_es_sql_de_bigquery(compilado):
    assert not compilado.get("graphErrors")
    for accion in compilado["tables"] + compilado["assertions"]:
        for clave in ("query", "incrementalQuery"):
            if clave in accion:
                sqlglot.parse_one(accion[clave], read="bigquery")


def test_mismas_tablas_y_pruebas_que_duckdb(compilado):
    locales = {t for capa in ("silver", "gold") for archivo in (RAIZ / "sql" / capa).glob("*.sql")
               for t in re.findall(r"^-- tabla: (\S+)$", archivo.read_text(), re.M)}
    assert {nombre(t) for t in compilado["tables"]} == locales
    assert {a["target"]["name"] for a in compilado["assertions"]} == {f.stem for f in (RAIZ / "sql" / "calidad").glob("*.sql")}


def test_gold_incremental_lee_solo_las_particiones_de_la_ventana(compilado):
    """En BigQuery, filtrar por la columna de partición es lo que hace que una carga diaria no relea todo gold."""
    incrementales = [t for t in compilado["tables"] if t["target"]["schema"] == "gold" and t["type"] == "incremental"]
    assert incrementales
    for tabla in incrementales:
        columna = tabla["bigquery"]["partitionBy"]
        assert re.search(rf"WHERE {columna} >= \(SELECT DATE_SUB\(MAX\({columna}\), INTERVAL 5 DAY\)", tabla["incrementalQuery"]), nombre(tabla)


def test_da_los_mismos_numeros_que_duckdb(compilado, local):
    con = duckdb.connect()
    bronze_hasta(con, local)
    ejecutar_dataform(con, compilado, incremental=False)
    mismos_numeros(con, compilado)


def test_la_ejecucion_incremental_da_los_mismos_numeros(compilado, local):
    """Primero hasta el día 10 completo; luego llega el resto y cada tabla incremental hace MERGE con su ventana."""
    con = duckdb.connect()
    bronze_hasta(con, local, date(2026, 9, 10))
    ejecutar_dataform(con, compilado, incremental=False)
    bronze_hasta(con, local)
    ejecutar_dataform(con, compilado, incremental=True)
    mismos_numeros(con, compilado)


def test_el_cargador_prepara_cada_dia_y_lo_carga_en_su_particion(raw, tmp_path):
    archivos = cargar_bigquery.preparar_archivos(raw, tmp_path, date(2026, 9, 3))
    assert {t for t, _, _ in archivos} == {"pedidos", "eventos", "rechazos_contrato", "liquidaciones", "extracto_banco"}
    lineas = [ln for ln in (raw / "eventos" / "2026-09-03.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    filas = {t: list(csv.DictReader(r.open(encoding="utf-8"))) for t, _, r in archivos}
    assert len(filas["eventos"]) == sum(not validar(ln) for ln in lineas)
    assert len(filas["eventos"]) + len(filas["rechazos_contrato"]) == len(lineas)
    assert {f["_fecha_archivo"] for t in filas for f in filas[t]} == {"2026-09-03"}

    con_bucket = cargar_bigquery.comandos("p", archivos, bucket="b")
    cargas = [c for c in con_bucket if "load" in c]
    assert all("--replace" in c for c in cargas)
    assert any(c[-3] == "p:bronze.eventos$20260903" and c[-2] == "gs://b/bronze/eventos_2026-09-03.csv" for c in cargas)
    assert all("gs://" not in " ".join(c) for c in cargar_bigquery.comandos("p", archivos))

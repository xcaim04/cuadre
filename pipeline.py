"""Corre el pipeline: bronze -> silver -> gold -> pruebas de calidad -> publicación.

Uso:
  uv run python pipeline.py [carpeta_raw] [archivo.duckdb]               carga todo y reconstruye silver y gold
  uv run python pipeline.py [carpeta_raw] [archivo.duckdb] --dia FECHA   carga diaria: solo archivos nuevos hasta FECHA
Sale con código 1 si alguna prueba de calidad falla.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

RAIZ = Path(__file__).parent
FUENTES = ("pedidos", "eventos", "liquidaciones", "extracto_banco")  # una carpeta por fuente, un archivo por día
VENTANA = 5  # días que se recalculan en cada carga diaria; un evento más atrasado va a cuarentena
CONTRATO = json.loads((RAIZ / "contratos" / "evento.json").read_text())
TIPOS = {"STRING": str}  # tipos del contrato que sabemos validar; uno nuevo falla con KeyError


def validar(linea: str) -> str | None:
    """Devuelve por qué la línea no cumple el contrato de eventos, o None si lo cumple."""
    try:
        evento = json.loads(linea)
    except json.JSONDecodeError:
        return "json_invalido"
    if not isinstance(evento, dict):
        return "json_invalido"
    campos = {c["name"]: c for c in CONTRATO}
    if extra := sorted(evento.keys() - campos.keys()):
        return f"campo_desconocido: {extra[0]}"
    for nombre, campo in campos.items():
        valor = evento.get(nombre)
        if valor is None:
            if campo["mode"] == "REQUIRED":
                return f"falta: {nombre}"
        elif not isinstance(valor, TIPOS[campo["type"]]):
            return f"tipo_invalido: {nombre}"
    return None


def cargar_eventos(con: duckdb.DuckDBPyConnection, archivo: Path) -> int:
    """Lo que cumple el contrato va a bronze.eventos; lo demás, a bronze.rechazos_contrato con su motivo."""
    campos = [c["name"] for c in CONTRATO]
    validos, rechazos = [], []
    for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        if motivo := validar(linea):
            rechazos.append([archivo.name, n, linea, motivo])
        else:
            evento = json.loads(linea)
            validos.append([evento.get(c) for c in campos] + [archivo.name, n])
    if validos:
        con.executemany(f"INSERT INTO bronze.eventos VALUES ({', '.join('?' * (len(campos) + 2))}, current_timestamp)", validos)
    if rechazos:
        con.executemany("INSERT INTO bronze.rechazos_contrato VALUES (?, ?, ?, ?, current_timestamp)", rechazos)
    return len(validos) + len(rechazos)


def cargar_bronze(con: duckdb.DuckDBPyConnection, raw: Path, hasta: date | None) -> list[date]:
    """Agrega a bronze cada archivo que no esté en meta.cargas. Devuelve las fechas de los archivos nuevos."""
    campos = [c["name"] for c in CONTRATO]
    con.execute(f"CREATE TABLE IF NOT EXISTS bronze.eventos ({', '.join(f'{c} VARCHAR' for c in campos)}, "
                "_archivo_origen VARCHAR, _linea INTEGER, _cargado_en TIMESTAMPTZ)")
    con.execute("CREATE TABLE IF NOT EXISTS bronze.rechazos_contrato "
                "(_archivo_origen VARCHAR, _linea INTEGER, contenido VARCHAR, motivo VARCHAR, _cargado_en TIMESTAMPTZ)")
    plantilla_csv = (RAIZ / "sql" / "bronze" / "csv.sql").read_text()
    nuevos = []
    for fuente in FUENTES:
        for archivo in sorted((raw / fuente).glob("*.*")):
            fecha = date.fromisoformat(archivo.stem)
            if hasta and fecha > hasta:
                continue
            md5 = hashlib.md5(archivo.read_bytes()).hexdigest()
            previo = con.execute("SELECT md5 FROM meta.cargas WHERE fuente = ? AND archivo = ?", [fuente, archivo.name]).fetchone()
            if previo:
                if previo[0] != md5:
                    raise ValueError(f"{fuente}/{archivo.name} cambió después de cargado; bronze no reescribe archivos")
                continue
            con.execute("BEGIN")  # el archivo y su registro en meta.cargas entran juntos o no entran
            if fuente == "eventos":
                filas = cargar_eventos(con, archivo)
            else:
                sql = plantilla_csv.replace("{{fuente}}", fuente).replace("{{archivo}}", str(archivo))
                filas = con.execute(sql.replace("{{nombre}}", archivo.name)).fetchone()[0]
            con.execute("INSERT INTO meta.cargas VALUES (?, ?, ?, ?, current_timestamp)", [fuente, archivo.name, md5, filas])
            con.execute("COMMIT")
            nuevos.append(fecha)
    return nuevos


def materializar(con: duckdb.DuckDBPyConnection, archivo: Path, valores: dict) -> None:
    """Un archivo SQL = una tabla, declarada en su cabecera con `-- tabla:`.

    Con `-- clave:` es incremental: reemplaza en una transacción las filas cuyas claves trae el resultado.
    Sin clave se reconstruye entera. Un archivo sin `-- tabla:` se ejecuta tal cual.
    """
    sql = archivo.read_text()
    for nombre, valor in valores.items():
        sql = sql.replace("{{" + nombre + "}}", str(valor))
    cabecera = dict(re.findall(r"^-- (tabla|clave): (\S+)$", sql, re.M))
    if "tabla" not in cabecera:
        con.execute(sql)
        return
    tabla, clave, consulta = cabecera["tabla"], cabecera.get("clave"), sql.strip().rstrip(";")
    if not clave:
        con.execute(f"CREATE OR REPLACE TABLE {tabla} AS {consulta}")
        return
    con.execute(f"CREATE OR REPLACE TEMP TABLE nuevo AS {consulta}")
    con.execute(f"CREATE TABLE IF NOT EXISTS {tabla} AS FROM nuevo LIMIT 0")
    con.execute("BEGIN")
    con.execute(f"DELETE FROM {tabla} WHERE {clave} IN (SELECT {clave} FROM nuevo)")
    con.execute(f"INSERT INTO {tabla} BY NAME FROM nuevo")
    con.execute("COMMIT")
    con.execute("DROP TABLE nuevo")


def ejecutar(raw: Path, db: Path | str = ":memory:", dia: date | None = None,
             seeds: Path = RAIZ / "seeds") -> duckdb.DuckDBPyConnection:
    """Sin `dia`, carga todo y reconstruye silver y gold. Con `dia`, carga los archivos nuevos hasta ese día y
    recalcula desde VENTANA días antes del archivo nuevo más viejo (o de `dia`, si no hay archivos nuevos)."""
    con = duckdb.connect(str(db))
    for esquema in ("meta", "bronze", "silver", "gold"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {esquema}")
    con.execute("CREATE TABLE IF NOT EXISTS meta.cargas (fuente VARCHAR, archivo VARCHAR, md5 VARCHAR, filas BIGINT, "
                "cargado_en TIMESTAMPTZ, PRIMARY KEY (fuente, archivo))")
    nuevos = cargar_bronze(con, raw, dia)
    # Un archivo nuevo puede traer eventos de hasta VENTANA días antes de su fecha.
    desde = date.min if dia is None else min([dia, *nuevos]) - timedelta(days=VENTANA)
    valores = {"seeds": seeds, "desde": desde, "ventana": VENTANA}
    for capa in ("silver", "gold"):
        for archivo in sorted((RAIZ / "sql" / capa).glob("*.sql")):
            materializar(con, archivo, valores)
    return con


def pruebas_calidad(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Cada archivo de sql/calidad devuelve las filas que rompen la regla: 0 filas = pasa."""
    return {
        archivo.stem: len(con.execute(archivo.read_text()).fetchall())
        for archivo in sorted((RAIZ / "sql" / "calidad").glob("*.sql"))
    }


def publicar_si_pasa(con: duckdb.DuckDBPyConnection, destino: Path) -> dict[str, int]:
    """Exporta gold a Parquet solo si pasan todas las pruebas de calidad; si alguna falla, no toca lo publicado."""
    resultado = pruebas_calidad(con)
    if not any(resultado.values()):
        destino.mkdir(parents=True, exist_ok=True)
        for (tabla,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'gold'").fetchall():
            con.execute(f"COPY gold.{tabla} TO '{destino / tabla}.parquet' (FORMAT parquet)")
    return resultado


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("raw", nargs="?", type=Path, default=RAIZ / "data" / "raw")
    argumentos.add_argument("db", nargs="?", default=RAIZ / "ruta_cobrada.duckdb")
    argumentos.add_argument("--dia", type=date.fromisoformat)
    a = argumentos.parse_args()
    con = ejecutar(a.raw, a.db, a.dia)
    resultado = publicar_si_pasa(con, RAIZ / "data" / "gold")
    for prueba, filas in resultado.items():
        print(f"{'OK   ' if filas == 0 else 'FALLA'} {prueba} ({filas} filas)")
    print(con.sql("SELECT origen, motivo, count(*) AS filas FROM silver.cuarentena GROUP BY ALL ORDER BY ALL"))
    print(con.sql("SELECT id_mensajero, deuda, deuda_0_2, deuda_3_7, deuda_mas_7 FROM gold.deuda_mensajero_dia "
                  "QUALIFY fecha = max(fecha) OVER () ORDER BY id_mensajero"))
    fallos = sum(filas > 0 for filas in resultado.values())
    print(f"{fallos} pruebas fallaron: gold no se publicó." if fallos else "Gold publicado en data/gold/.")
    sys.exit(1 if fallos else 0)

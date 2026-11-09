"""Corre el pipeline: bronze -> silver -> gold -> pruebas de calidad.

Uso: uv run python pipeline.py [carpeta_raw] [archivo.duckdb]
Sale con código 1 si alguna prueba de calidad falla.
"""

import json
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).parent
CAPAS = ("bronze", "silver", "gold")
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


def cargar_eventos(con: duckdb.DuckDBPyConnection, raw: Path) -> None:
    """Bronze de eventos: lo que cumple el contrato va a bronze.eventos; lo demás, a bronze.rechazos_contrato con su motivo."""
    campos = [c["name"] for c in CONTRATO]
    con.execute(f"CREATE OR REPLACE TABLE bronze.eventos ({', '.join(f'{c} VARCHAR' for c in campos)}, "
                "_archivo_origen VARCHAR, _linea INTEGER, _cargado_en TIMESTAMPTZ)")
    con.execute("CREATE OR REPLACE TABLE bronze.rechazos_contrato "
                "(_archivo_origen VARCHAR, _linea INTEGER, contenido VARCHAR, motivo VARCHAR, _cargado_en TIMESTAMPTZ)")
    validos, rechazos = [], []
    for archivo in sorted((raw / "eventos").glob("*.jsonl")):
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


def ejecutar(raw: Path, db: Path | str = ":memory:") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db))
    for capa in CAPAS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {capa}")
        for archivo in sorted((RAIZ / "sql" / capa).glob("*.sql")):
            con.execute(archivo.read_text().replace("{{raw}}", str(raw)))
        if capa == "bronze":
            cargar_eventos(con, raw)
    return con


def pruebas_calidad(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Cada archivo de sql/calidad devuelve las filas que rompen la regla: 0 filas = pasa."""
    return {
        archivo.stem: len(con.execute(archivo.read_text()).fetchall())
        for archivo in sorted((RAIZ / "sql" / "calidad").glob("*.sql"))
    }


if __name__ == "__main__":
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "data" / "raw"
    db = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "ruta_cobrada.duckdb"
    con = ejecutar(raw, db)
    fallos = 0
    for prueba, filas in pruebas_calidad(con).items():
        print(f"{'OK   ' if filas == 0 else 'FALLA'} {prueba} ({filas} filas)")
        fallos += filas > 0
    print(con.sql("SELECT schema_name || '.' || table_name AS tabla, estimated_size AS filas "
                  "FROM duckdb_tables() ORDER BY tabla"))
    print(con.sql("SELECT motivo, count(*) AS lineas FROM bronze.rechazos_contrato GROUP BY motivo ORDER BY motivo"))
    sys.exit(1 if fallos else 0)

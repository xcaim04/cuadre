"""Carga los archivos diarios a la capa bronze de BigQuery, tal cual llegan y todo como texto.

Uso: uv run python cargar_bigquery.py --proyecto <id> [--dia AAAA-MM-DD] [--bucket <nombre>] [--mostrar]

Cada archivo se carga con --replace en la partición de su día: repetir la carga de un día no duplica filas.
Los eventos se revisan antes contra contratos/evento.json, igual que en la versión local: lo que no lo cumple
va a bronze.rechazos_contrato. Con --bucket, cada archivo sube primero a gs://<bucket>/bronze/ y BigQuery lo
carga desde ahí; sin él, se carga desde este equipo, que es lo que permite el sandbox gratis.
Necesita gcloud y bq con la sesión iniciada; --mostrar solo imprime los comandos.
Después: cd dataform && npx dataform run .
"""

import argparse
import csv
import shlex
import subprocess
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from pipeline import CONTRATO, FUENTES, RAIZ, leer_eventos

# Columnas de cada tabla de bronze, sin las que añade la carga (_archivo_origen, _cargado_en, _fecha_archivo).
COLUMNAS = {
    "pedidos": ["id_pedido", "actualizado_en", "id_mensajero", "cliente", "direccion", "importe"],
    "eventos": [c["name"] for c in CONTRATO] + ["_linea"],
    "liquidaciones": ["fecha", "mensajero", "importe"],
    "extracto_banco": ["fecha", "referencia", "importe"],
    "rechazos_contrato": ["_linea", "contenido", "motivo"],
}
ALIAS = RAIZ / "seeds" / "alias_mensajeros.csv"


def preparar_archivos(raw: Path, destino: Path, dia: date | None = None) -> list[tuple[str, date, Path]]:
    """Un CSV por tabla y día, con las columnas de carga añadidas. Devuelve (tabla, día, archivo)."""
    cargado_en = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
    salida = []

    def escribir(tabla, fecha, nombre, filas):
        ruta = destino / f"{tabla}_{fecha}.csv"
        with ruta.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNAS[tabla] + ["_archivo_origen", "_cargado_en", "_fecha_archivo"])
            w.writerows(fila + [nombre, cargado_en, fecha] for fila in filas)
        salida.append((tabla, fecha, ruta))

    for fuente in FUENTES:
        for archivo in sorted((raw / fuente).glob("*.*")):
            fecha = date.fromisoformat(archivo.stem)
            if dia and fecha != dia:
                continue
            if fuente == "eventos":
                validos, rechazos = leer_eventos(archivo)
                escribir("eventos", fecha, archivo.name, validos)
                escribir("rechazos_contrato", fecha, archivo.name, rechazos)
                continue
            with archivo.open(encoding="utf-8", newline="") as f:
                lector = csv.DictReader(f)
                if lector.fieldnames != COLUMNAS[fuente]:
                    raise SystemExit(f"{fuente}/{archivo.name}: las columnas deben ser {COLUMNAS[fuente]}")
                escribir(fuente, fecha, archivo.name, [[fila[c] for c in COLUMNAS[fuente]] for fila in lector])
    if not salida:
        raise SystemExit(f"No hay archivos para cargar en {raw}" + (f" del día {dia}" if dia else ""))
    return salida


def comandos(proyecto: str, archivos: list[tuple[str, date, Path]], bucket: str = "", ubicacion: str = "US") -> list[list[str]]:
    bq = ["bq", f"--project_id={proyecto}", f"--location={ubicacion}"]
    lista = [bq + ["mk", "--force", "--dataset", f"{proyecto}:bronze"]]

    def esquema(tabla):
        return ",".join(f"{c}:{'INTEGER' if c == '_linea' else 'STRING'}" for c in COLUMNAS[tabla]) + \
            ",_archivo_origen:STRING,_cargado_en:TIMESTAMP,_fecha_archivo:DATE"

    for tabla in dict.fromkeys(t for t, _, _ in archivos):
        lista.append(bq + ["mk", "--force", "--table", "--time_partitioning_field=_fecha_archivo",
                           "--time_partitioning_type=DAY", f"{proyecto}:bronze.{tabla}", esquema(tabla)])

    def subir(archivo: Path) -> str:
        if not bucket:
            return str(archivo)
        lista.append(["gcloud", "storage", "cp", str(archivo), f"gs://{bucket}/bronze/{archivo.name}", f"--project={proyecto}"])
        return f"gs://{bucket}/bronze/{archivo.name}"

    carga = ["load", "--replace", "--source_format=CSV", "--skip_leading_rows=1", "--allow_quoted_newlines"]
    for tabla, fecha, archivo in archivos:
        origen = subir(archivo)
        lista.append(bq + carga + [f"{proyecto}:bronze.{tabla}${fecha:%Y%m%d}", origen, esquema(tabla)])
    lista.append(bq + carga + [f"{proyecto}:bronze.alias_mensajeros", subir(ALIAS), "alias:STRING,id_mensajero:STRING"])
    return lista


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--proyecto", required=True, help="ID del proyecto de Google Cloud")
    p.add_argument("--dia", type=date.fromisoformat, help="solo los archivos de ese día; sin él, todos")
    p.add_argument("--bucket", default="", help="bucket de Cloud Storage; sin él, se carga desde este equipo")
    p.add_argument("--ubicacion", default="US")
    p.add_argument("--raw", type=Path, default=RAIZ / "data" / "raw")
    p.add_argument("--mostrar", action="store_true", help="solo imprimir los comandos")
    args = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        archivos = preparar_archivos(args.raw, Path(tmp), args.dia)
        for comando in comandos(args.proyecto, archivos, args.bucket, args.ubicacion):
            print("$", shlex.join(comando))
            if not args.mostrar:
                subprocess.run(comando, check=True)

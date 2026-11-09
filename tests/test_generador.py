"""El generador es determinista, trae los defectos prometidos y su verdad cuadra con sus propios archivos."""

import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal

import pytest

from generar_datos import MENSAJEROS, generar
from pipeline import validar


def eventos_validos(raw):
    """(archivo, evento) de cada línea que cumple el contrato."""
    return [(a.stem, json.loads(linea)) for a in sorted((raw / "eventos").glob("*.jsonl"))
            for linea in a.read_text(encoding="utf-8").splitlines() if not validar(linea)]


def leer_csv(ruta):
    with ruta.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_misma_semilla_mismos_archivos(raw, tmp_path):
    otra = tmp_path / "otra"
    generar(otra)
    archivos = sorted(p.relative_to(raw) for p in raw.rglob("*") if p.is_file())
    assert archivos == sorted(p.relative_to(otra) for p in otra.rglob("*") if p.is_file())
    assert all((raw / a).read_bytes() == (otra / a).read_bytes() for a in archivos)


def test_no_pisa_una_carpeta_con_datos(raw):
    with pytest.raises(FileExistsError):
        generar(raw)


def test_trae_los_defectos_prometidos(raw):
    eventos = eventos_validos(raw)
    assert max(Counter(e["id_evento"] for _, e in eventos).values()) > 1, "sin duplicados"
    assert any(e["ocurrido_en"][:10] < archivo for archivo, e in eventos), "sin eventos tardíos"
    por_archivo = defaultdict(list)
    for archivo, e in eventos:
        por_archivo[archivo].append(e["ocurrido_en"])
    assert any(horas != sorted(horas) for horas in por_archivo.values()), "sin desorden"
    assert {e["tipo"] for _, e in eventos} == {"entrega", "rechazo", "devolucion"}
    pedidos = [p for a in (raw / "pedidos").glob("*.csv") for p in leer_csv(a)]
    assert max(Counter(p["id_pedido"] for p in pedidos).values()) > 1, "sin pedidos editados"
    nombres = {fila["mensajero"] for fila in leer_csv(raw / "liquidaciones.csv")}
    assert len(nombres) > len(MENSAJEROS), "sin alias de mensajeros"
    lineas = [linea for a in (raw / "eventos").glob("*.jsonl") for linea in a.read_text(encoding="utf-8").splitlines()]
    assert any(validar(linea) for linea in lineas), "sin líneas que rompan el contrato"


def test_la_verdad_cuadra_con_los_archivos(raw):
    """Deuda final = entregas − devoluciones − liquidaciones, contando cada evento una vez."""
    unicos = {e["id_evento"]: e for _, e in eventos_validos(raw)}.values()
    deuda = defaultdict(Decimal)
    for e in unicos:
        signo = {"entrega": 1, "devolucion": -1, "rechazo": 0}[e["tipo"]]
        deuda[e["id_mensajero"]] += signo * Decimal(e["importe"] or 0)
    alias = {nombre: m for m, nombres in MENSAJEROS.items() for nombre in nombres}
    liquidado = Decimal(0)
    for fila in leer_csv(raw / "liquidaciones.csv"):
        deuda[alias[fila["mensajero"]]] -= Decimal(fila["importe"])
        liquidado += Decimal(fila["importe"])

    verdad = json.loads((raw / "verdad.json").read_text())["deuda_al_cierre"]
    ultimo = max(v["fecha"] for v in verdad)
    assert {v["id_mensajero"]: Decimal(v["deuda"]) for v in verdad if v["fecha"] == ultimo} == dict(deuda)
    depositado = sum(Decimal(f["importe"]) for f in leer_csv(raw / "extracto_banco.csv"))
    assert 0 < depositado <= liquidado

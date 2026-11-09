"""Bronze guarda las fuentes tal cual y aparta, con su motivo, cada evento que no cumple el contrato."""

import csv

from pipeline import ejecutar


def contar_filas_csv(*archivos):
    total = 0
    for a in archivos:
        with a.open(encoding="utf-8") as f:
            total += sum(1 for _ in csv.DictReader(f))
    return total


def contar(con, tabla, donde="true"):
    return con.execute(f"SELECT count(*) FROM bronze.{tabla} WHERE {donde}").fetchone()[0]


def test_bronze_carga_todas_las_filas(raw):
    con = ejecutar(raw)
    lineas = [linea for a in (raw / "eventos").glob("*.jsonl") for linea in a.read_text(encoding="utf-8").splitlines()]
    assert contar(con, "eventos") + contar(con, "rechazos_contrato") == len(lineas)
    assert contar(con, "rechazos_contrato") > 0
    assert contar(con, "pedidos") == contar_filas_csv(*(raw / "pedidos").glob("*.csv"))
    assert contar(con, "liquidaciones") == contar_filas_csv(raw / "liquidaciones.csv")
    assert contar(con, "extracto_banco") == contar_filas_csv(raw / "extracto_banco.csv")
    for tabla in ("pedidos", "liquidaciones", "extracto_banco", "eventos"):
        assert contar(con, tabla, "_archivo_origen IS NULL OR _cargado_en IS NULL") == 0


def test_contrato_aparta_cada_linea_mala_con_su_motivo(tmp_path):
    (tmp_path / "pedidos").mkdir()
    (tmp_path / "pedidos" / "2026-09-01.csv").write_text("id_pedido,actualizado_en,id_mensajero,cliente,direccion,importe\n")
    (tmp_path / "liquidaciones.csv").write_text("fecha,mensajero,importe\n")
    (tmp_path / "extracto_banco.csv").write_text("fecha,referencia,importe\n")
    base = '"id_pedido": "P1", "id_mensajero": "M01", "tipo": "entrega", "ocurrido_en": "2026-09-01 13:00:00"'
    (tmp_path / "eventos").mkdir()
    (tmp_path / "eventos" / "2026-09-01.jsonl").write_text("\n".join([
        '{"id_evento": "E1", ' + base + ', "importe": "100.00"}',
        '{"id_evento": "E2", ' + base + '}',  # importe es opcional: un rechazo no lo trae
        '{"id_evento": "E3", ' + base + ', "importe": "1", "propina": "5"}',
        '{"id_evento": "E4", "id_pedido": "P1", "tipo": "entrega", "ocurrido_en": "2026-09-01 13:00:00"}',
        '{"id_evento": "E5", ' + base + ', "importe": 100.0}',
        '{"id_evento": "E6", ' + base.replace('"P1"', "null") + '}',
        '{"id_evento": "E7", "id_pedido": "P1',
        '["no", "es", "un", "objeto"]',
        "",
    ]) + "\n")
    con = ejecutar(tmp_path)
    assert con.execute("SELECT list(id_evento ORDER BY _linea) FROM bronze.eventos").fetchone()[0] == ["E1", "E2"]
    assert contar(con, "eventos", "id_evento = 'E2' AND importe IS NULL") == 1
    assert con.execute("SELECT list(motivo ORDER BY _linea) FROM bronze.rechazos_contrato").fetchone()[0] == [
        "campo_desconocido: propina", "falta: id_mensajero", "tipo_invalido: importe", "falta: id_pedido",
        "json_invalido", "json_invalido",
    ]

"""Archivos crudos chiquitos hechos a mano para probar una regla a la vez."""

import json

from pipeline import ejecutar

PEDIDOS = "id_pedido,actualizado_en,id_mensajero,cliente,direccion,importe\n"
P1 = PEDIDOS + "P1,2026-09-01 10:00:00,M01,Ana López,Calle 1 #1,100.00\n"
LIQUIDACIONES = "fecha,mensajero,importe\n"
EXTRACTO = "fecha,referencia,importe\n"


def evento(id_evento, tipo="entrega", cuando="2026-09-01 15:00:00", importe="100.00", pedido="P1", mensajero="M01"):
    return json.dumps({"id_evento": id_evento, "id_pedido": pedido, "id_mensajero": mensajero, "tipo": tipo,
                       "ocurrido_en": cuando, "importe": importe})


def escribir(tmp_path, eventos: dict[str, list[str]], pedidos=P1, liquidaciones=LIQUIDACIONES, extracto=EXTRACTO):
    """eventos: día del archivo -> líneas."""
    (tmp_path / "pedidos").mkdir(parents=True)
    (tmp_path / "pedidos" / "2026-09-01.csv").write_text(pedidos, encoding="utf-8")
    (tmp_path / "eventos").mkdir()
    for dia, lineas in eventos.items():
        (tmp_path / "eventos" / f"{dia}.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    (tmp_path / "liquidaciones.csv").write_text(liquidaciones, encoding="utf-8")
    (tmp_path / "extracto_banco.csv").write_text(extracto, encoding="utf-8")
    return tmp_path


def correr(tmp_path, eventos, **archivos):
    return ejecutar(escribir(tmp_path, eventos, **archivos))


def uno(con, sql):
    return con.execute(sql).fetchone()[0]

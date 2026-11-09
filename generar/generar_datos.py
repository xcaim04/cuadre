"""Genera los archivos crudos (sintéticos) de Ruta Cobrada, una mensajería ficticia que cobra contra entrega.

Los defectos son a propósito: pedidos editados después de creados, eventos duplicados,
desordenados o que llegan días tarde, entregas marcadas sin cobro, líneas que no cumplen el contrato, nombres de
mensajero escritos de varias formas en la planilla de caja y depósitos que agrupan días.

También escribe verdad.json: la deuda real de cada mensajero al cierre de cada día.
El pipeline nunca la lee; solo la usan las pruebas.

Uso: uv run python generar/generar_datos.py [carpeta_salida]
"""

import csv
import json
import random
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

SEMILLA = 7
INICIO = date(2026, 9, 1)
DIAS = 60
FIN = INICIO + timedelta(days=DIAS - 1)
CENTAVO = Decimal("0.01")

# id: formas en que el cajero escribe el nombre en la planilla (la primera es la oficial)
MENSAJEROS = {
    "M01": ["Yoandry Pérez", "yoandry perez", "YOANDRY  PEREZ", "Yoyi"],
    "M02": ["Dayana Rodríguez", "dayana rodriguez", "Dayana Rodriguez "],
    "M03": ["Osmany Fernández", "Osmany Fernandez", "OSMANY FERNÁNDEZ"],
    "M04": ["Yusleidy Gómez", "yusleidy gomez", "Yusle"],
    "M05": ["Reinier Castillo", "reinier  castillo", "REINIER CASTILLO"],
    "M06": ["Mailén Suárez", "Mailen Suarez", "mailén suárez"],
    "M07": ["Yordanis Díaz", "yordanis diaz", "Yordanis Diaz "],
    "M08": ["Lisandra Martínez", "lisandra martinez", "LISANDRA MARTINEZ"],
}
CLIENTES = ["Ana López", "Raúl Hernández", "Marta Ruiz", "Pedro Valdés", "Iris Molina", "Jorge Cabrera",
            "Lázaro Torres", "Elena Ortiz", "Rosa Peña", "Camilo Reyes", "Nidia Blanco", "Félix Morales"]

P_PENDIENTE = 0.03   # sin entrega todavía
P_SIN_COBRO = 0.3    # de los pendientes: la app los marca entregados sin cobro, pero no hubo efectivo
P_RECHAZO = 0.08     # el cliente no acepta en la puerta
P_EDICION = 0.15     # el pedido cambia de importe o dirección después de creado
P_DEVOLUCION = 0.03  # efectivo devuelto al cliente después de cobrar
P_TARDE = 0.05       # el evento llega de 1 a 4 días después
P_DUPLICADO = 0.03   # el evento se reenvía con el mismo id
P_BASURA = 0.3       # probabilidad de que un archivo diario traiga una línea que no cumple el contrato
P_LIQUIDA = 0.85     # el mensajero pasa por la oficina al final del día
P_PARCIAL = 0.2      # la liquidación se anota en dos pagos


def dias():
    return (INICIO + timedelta(days=i) for i in range(DIAS))


def momento(rnd, dia: date, desde: int, hasta: int) -> datetime:
    return datetime.combine(dia, time(rnd.randint(desde, hasta - 1), rnd.randint(0, 59)))


def importe(rnd) -> Decimal:
    return (Decimal(rnd.randrange(30000, 900000, 50)) / 100).quantize(CENTAVO)


def generar(salida: Path, semilla: int = SEMILLA) -> None:
    if salida.exists() and any(salida.iterdir()):
        raise FileExistsError(f"{salida} ya tiene archivos; genera en una carpeta vacía")
    rnd = random.Random(semilla)
    pedidos = defaultdict(list)       # día del archivo -> filas
    eventos = defaultdict(list)       # día en que llega el evento -> líneas
    movimientos = defaultdict(Decimal)  # (mensajero, día) -> cobros menos devoluciones
    n_pedido = n_evento = 0

    def evento(tipo, id_pedido, mensajero, cuando: datetime, monto):
        nonlocal n_evento
        n_evento += 1
        linea = json.dumps({
            "id_evento": f"E{n_evento:06d}", "id_pedido": id_pedido, "id_mensajero": mensajero, "tipo": tipo,
            "ocurrido_en": str(cuando), "importe": None if monto is None else str(monto),
        }, ensure_ascii=False)
        llegada = cuando.date() + timedelta(days=rnd.randint(1, 4) if rnd.random() < P_TARDE else 0)
        eventos[llegada].append(linea)
        if rnd.random() < P_DUPLICADO:
            eventos[llegada + timedelta(days=rnd.randint(0, 1))].append(linea)

    for dia in dias():
        for _ in range(rnd.randint(25, 40)):
            n_pedido += 1
            id_pedido, mensajero = f"P{n_pedido:05d}", rnd.choice(list(MENSAJEROS))
            creado, cliente = momento(rnd, dia, 8, 12), rnd.choice(CLIENTES)
            versiones = [(creado, importe(rnd), f"Calle {rnd.randint(1, 300)} #{rnd.randint(1, 999)}")]
            if rnd.random() < P_EDICION:
                editado = creado + timedelta(minutes=rnd.randint(30, 3 * 24 * 60))
                _, monto, direccion = versiones[0]
                if rnd.random() < 0.5:
                    monto = importe(rnd)
                else:
                    direccion = f"Calle {rnd.randint(1, 300)} #{rnd.randint(1, 999)}"
                if editado.date() <= FIN:
                    versiones.append((editado, monto, direccion))
            for cuando, monto, direccion in versiones:
                pedidos[cuando.date()].append([id_pedido, cuando, mensajero, cliente, direccion, monto])

            entrega = momento(rnd, dia + timedelta(days=rnd.randint(0, 2)), 13, 20)
            destino = rnd.random()
            if entrega.date() > FIN or destino < P_PENDIENTE:
                if entrega.date() <= FIN and rnd.random() < P_SIN_COBRO:
                    evento("entrega", id_pedido, mensajero, entrega, None)
                continue
            if destino < P_PENDIENTE + P_RECHAZO:
                evento("rechazo", id_pedido, mensajero, entrega, None)
                continue
            cobrado = [m for cuando, m, _ in versiones if cuando <= entrega][-1]
            evento("entrega", id_pedido, mensajero, entrega, cobrado)
            movimientos[mensajero, entrega.date()] += cobrado
            if rnd.random() < P_DEVOLUCION:
                devuelto_en = entrega + timedelta(days=rnd.randint(1, 3))
                devuelto = cobrado if rnd.random() < 0.5 else (cobrado / 2).quantize(CENTAVO)
                if devuelto_en.date() <= FIN:
                    evento("devolucion", id_pedido, mensajero, devuelto_en, devuelto)
                    movimientos[mensajero, devuelto_en.date()] -= devuelto

    # Líneas que no cumplen el contrato: no son movimientos reales y no cuentan en la verdad.
    basura = [
        '{"id_evento": "E-roto", "id_pedido": "P0',
        '{"id_evento": "X1", "id_pedido": "P00001", "id_mensajero": "M01", "tipo": "entrega", '
        '"ocurrido_en": "2026-09-01 13:00:00", "importe": "100.00", "propina": "20"}',
        '{"id_evento": "X2", "id_pedido": "P00001", "tipo": "entrega", "ocurrido_en": "2026-09-01 13:00:00", '
        '"importe": "100.00"}',
        '{"id_evento": "X3", "id_pedido": "P00001", "id_mensajero": "M01", "tipo": "entrega", '
        '"ocurrido_en": "2026-09-01 13:00:00", "importe": 100.0}',
    ]
    for lineas in eventos.values():
        if rnd.random() < P_BASURA:
            lineas.append(rnd.choice(basura))
        rnd.shuffle(lineas)

    deuda = dict.fromkeys(MENSAJEROS, Decimal(0))
    caja, siguiente_deposito = Decimal(0), INICIO + timedelta(days=rnd.randint(2, 4))
    liquidaciones, depositos, verdad = [], [], []
    for dia in dias():
        for mensajero, alias in MENSAJEROS.items():
            deuda[mensajero] += movimientos[mensajero, dia]
            if deuda[mensajero] > 0 and rnd.random() < P_LIQUIDA:
                monto = (deuda[mensajero] * rnd.randint(60, 100) // 100 // 10 * 10).quantize(CENTAVO)
                mitad = (monto // 20 * 10).quantize(CENTAVO)
                for pago in ([mitad, monto - mitad] if rnd.random() < P_PARCIAL else [monto]):
                    if pago > 0:
                        liquidaciones.append([dia, rnd.choice(alias), pago])
                        deuda[mensajero] -= pago
                        caja += pago
            verdad.append({"fecha": str(dia), "id_mensajero": mensajero, "deuda": str(deuda[mensajero])})
        if dia >= siguiente_deposito and caja > 0:
            depositos.append([dia, f"DEP-{len(depositos) + 1:04d}", caja])
            caja, siguiente_deposito = Decimal(0), dia + timedelta(days=rnd.randint(2, 4))

    (salida / "pedidos").mkdir(parents=True)
    (salida / "eventos").mkdir()
    for dia, filas in pedidos.items():
        escribir(salida / "pedidos" / f"{dia}.csv",
                 ["id_pedido", "actualizado_en", "id_mensajero", "cliente", "direccion", "importe"], filas)
    for dia, lineas in eventos.items():
        (salida / "eventos" / f"{dia}.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    escribir(salida / "liquidaciones.csv", ["fecha", "mensajero", "importe"], liquidaciones)
    escribir(salida / "extracto_banco.csv", ["fecha", "referencia", "importe"], depositos)
    (salida / "verdad.json").write_text(json.dumps({"semilla": semilla, "deuda_al_cierre": verdad}, indent=1))


def escribir(ruta: Path, encabezado, filas) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(encabezado)
        w.writerows(filas)


if __name__ == "__main__":
    generar(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "data" / "raw")

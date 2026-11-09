# Ruta Cobrada

Conciliación del efectivo de una mensajería que cobra contra entrega: cuánto dinero tiene cada mensajero ahora mismo y por qué la caja no cuadra con lo vendido.

El número piloto, que debe cuadrar al centavo:

> deuda del mensajero = cobrado − liquidado − devoluciones

Un pedido rechazado en la puerta nunca se cobra; una devolución es efectivo devuelto al cliente después de cobrar. El [glosario del plan](docs/plan-sprints.md#glosario) fija cada término.

Pipeline bronze → silver → gold en DuckDB (local) y Dataform sobre BigQuery, con cargas incrementales, datos que llegan tarde, historial SCD tipo 2 y pruebas de calidad.

**Estado:** sprint 2 (reglas de silver). El plan completo está en [docs/plan-sprints.md](docs/plan-sprints.md).

## Fuentes

Los datos son sintéticos: [generar/generar_datos.py](generar/generar_datos.py) los crea con semilla fija para 8 mensajeros y 60 días, con defectos a propósito.

| Archivo | Qué es | Defectos |
|---|---|---|
| `pedidos/AAAA-MM-DD.csv` | Pedidos de la tienda, uno por día | Un pedido editado reaparece con nuevo importe o dirección |
| `eventos/AAAA-MM-DD.jsonl` | Entregas, rechazos y devoluciones de la mensajería | Duplicados, desordenados, un 5 % llega de 1 a 4 días tarde y algunas líneas no cumplen el contrato |
| `liquidaciones.csv` | Planilla del cajero | El nombre del mensajero escrito de varias formas y pagos partidos en dos |
| `extracto_banco.csv` | Depósitos de la oficina | Un depósito agrupa varios días |
| `verdad.json` | Deuda real de cada mensajero al cierre de cada día | Solo la leen las pruebas, nunca el pipeline |

El generador no escribe en una carpeta que ya tenga archivos, para no pisar datos.

## Reglas de bronze

- Bronze guarda cada fuente tal cual, todo como texto, con el archivo de origen y la hora de carga.
- Un evento que no cumple [el contrato](contratos/evento.json) va a `bronze.rechazos_contrato` con su motivo, en lugar de romper la carga o perderse en silencio.

## Reglas de silver

- **Duplicados:** un evento repetido con el mismo `id_evento` cuenta una vez; vale la primera copia que llegó.
- **Estado vigente:** el estado de un pedido es el de su evento válido con mayor `ocurrido_en`, no el del último que llegó.
- **Historial (SCD tipo 2):** cada versión de un pedido vale desde su `actualizado_en` hasta la versión siguiente, y el importe cobrable es el de la versión vigente al entregar.
- **Alias de mensajeros:** un nombre se compara sin mayúsculas, tildes ni espacios de más, y se traduce a su id con [el seed de alias](seeds/alias_mensajeros.csv).
- **Cuarentena:** lo que no se puede usar va a `silver.cuarentena` con su motivo (`entrega_sin_cobro`, `devolucion_sin_entrega`, `pedido_desconocido`, `mensajero_desconocido`, `tipo_desconocido`, `dato_invalido`, `importe_no_positivo`) y nunca cuenta como cero.
- **Fuentes de sistemas propios:** pedidos y extracto bancario vienen de sistemas, no de personas; un tipo inválido ahí detiene el pipeline en lugar de esconderse en cuarentena.

## Ejecutar

```bash
uv sync
uv run python generar/generar_datos.py
uv run python pipeline.py
uv run pytest
```

# Ruta Cobrada

Conciliación del efectivo de una mensajería que cobra contra entrega: cuánto dinero tiene cada mensajero ahora mismo y por qué la caja no cuadra con lo vendido.

El número piloto, que debe cuadrar al centavo:

> deuda del mensajero = cobrado − liquidado − devoluciones

Un pedido rechazado en la puerta nunca se cobra; una devolución es efectivo devuelto al cliente después de cobrar. El [glosario del plan](docs/plan-sprints.md#glosario) fija cada término.

Pipeline bronze → silver → gold en DuckDB (local) y Dataform sobre BigQuery, con cargas incrementales, datos que llegan tarde, historial SCD tipo 2 y pruebas de calidad.

**Estado:** sprint 0 (esqueleto). El plan completo está en [docs/plan-sprints.md](docs/plan-sprints.md).

## Ejecutar

```bash
uv sync
uv run pytest
```

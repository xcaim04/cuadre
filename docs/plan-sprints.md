# Ruta Cobrada: plan de desarrollo por sprints

## Contexto

Proyecto de portafolio de ingeniería de datos: BigQuery, capas bronze/silver/gold, Dataform, pytest, merge requests y una página de BI. El criterio de éxito es que el número piloto cuadre y que cada regla se explique en una frase.

Ruta Cobrada concilia el efectivo de una mensajería que cobra contra entrega. El número piloto, que debe cuadrar al centavo con la verdad que guarda el generador:

> deuda del mensajero = cobrado − liquidado − devoluciones

Complementa a [La Ceiba](https://github.com/xcaim04/la-ceiba-data), que recalcula todo en cada carga. Aquí lo central es lo que La Ceiba no enseña: cargas incrementales, datos que llegan tarde, SCD tipo 2, particiones y clustering en BigQuery y contratos de esquema.

## Glosario

Cada término tiene un solo significado en el generador, el SQL y las pruebas.

- **Cobrado:** efectivo que el mensajero recibe del cliente al entregar.
- **Rechazado:** pedido que el cliente no acepta en la puerta. Nunca se cobra y no suma ni resta deuda.
- **Devolución:** efectivo que el mensajero devuelve al cliente después de cobrar, con aprobación de la oficina. Resta deuda.
- **Liquidado:** efectivo que el mensajero entrega en la oficina. Resta deuda.
- **Depositado:** efectivo que la oficina ingresa en el banco. No toca la deuda del mensajero.

## Forma de trabajo

- Una rama por sprint (`sprint-N-tema`) con su merge request hacia `staging`. Al cerrar el sprint, `staging` pasa a `main` y se etiqueta la versión.
- Definición de hecho: `uv run pytest` en verde, cada regla nueva con su frase en el README y su prueba, y el número piloto cuadrando con la verdad del generador.
- Duración de referencia: una semana por sprint.

## Sprints

### Sprint 0: esqueleto (v0.0.1)
- Repo con uv, este plan y CI de GitHub Actions que corre pytest en cada merge request.

### Sprint 1: generador sintético y bronze (v0.1.0)
- `generar/generar_datos.py` genera las fuentes con semilla fija, 8 mensajeros y unos 60 días:
  - `pedidos/AAAA-MM-DD.csv`: pedidos diarios, con ediciones posteriores de importe y dirección.
  - `eventos/AAAA-MM-DD.jsonl`: entregas, rechazos y devoluciones, con duplicados, desorden y un 5 % que llega de 1 a 4 días tarde.
  - `liquidaciones.csv`: la planilla del cajero, con alias del mensajero escritos de varias formas y pagos parciales.
  - `extracto_banco.csv`: depósitos que agrupan varios días.
  - `verdad.json`: la deuda real por mensajero y día. El pipeline nunca la lee; solo la usan las pruebas.
- `sql/bronze/*.sql`: todo como texto, más `_archivo_origen` y `_cargado_en`.
- Contrato de eventos en `contratos/evento.json` (columnas y tipos). Un evento que no lo cumple va a `bronze.rechazos_contrato` en lugar de romper la carga en silencio.
- Pruebas: el generador es determinista y el contrato aparta un evento malformado.

### Sprint 2: reglas de silver (v0.2.0)
Cada regla tiene su frase en el README y su prueba.
- **Duplicados:** un evento repetido con el mismo `id_evento` cuenta una vez.
- **Estado vigente:** el estado del pedido sale del evento con mayor `ocurrido_en`, no del último que llegó.
- **SCD tipo 2:** `silver.pedidos_historial` guarda cada versión del pedido con `valido_desde` y `valido_hasta`. El importe cobrable es el vigente en el momento de la entrega.
- **Alias de mensajeros:** se normalizan (minúsculas, sin tildes ni espacios dobles) y se mapean con `seeds/alias_mensajeros.csv`.
- **Cuarentena:** una entrega sin cobro registrado, o un cobro sin entrega, va a `silver.cuarentena` con su motivo; nunca cuenta como cero.

### Sprint 3: gold y calidad (v0.3.0)
- `gold.deuda_mensajero_dia`: deuda acumulada por mensajero y día, con antigüedad en tramos (0–2, 3–7, más de 7 días).
- `gold.cierre_caja`: por día, lo cobrado, devuelto, liquidado y depositado, y dónde está el efectivo (en mensajeros, en la oficina o en el banco).
- `gold.pedidos_perdidos`: pedidos sin entrega ni rechazo válidos más de 3 días después de creados, con el motivo si tienen eventos en cuarentena.
- `sql/calidad/*.sql`, donde cero filas significa que pasa (12 pruebas):
  - claves únicas de eventos y pedidos;
  - importes positivos;
  - historial SCD sin dos versiones que empiecen a la vez;
  - lo cobrado es el importe vigente al entregar;
  - un alias lleva a un solo mensajero;
  - no se devuelve más de lo cobrado;
  - la deuda final cuadra con silver y los tramos de antigüedad suman la deuda;
  - los totales del cierre de caja son los de silver;
  - la cuarentena queda por debajo del 2 % de los eventos;
  - lo depositado acumulado hasta cada fecha no supera lo liquidado acumulado hasta esa fecha (un depósito puede agrupar varios días).
- `pipeline.py` no publica gold si falla alguna prueba de calidad.
- Prueba clave: `gold.deuda_mensajero_dia` es igual a `verdad.json`, centavo a centavo.

### Sprint 4: carga incremental y datos tardíos (v0.4.0)
- `pipeline.py --dia AAAA-MM-DD` procesa solo los archivos nuevos de ese día.
- Escritura idempotente con `MERGE` o `INSERT OR REPLACE` de DuckDB y clave única.
- Ventana de reproceso: cada carga recalcula los últimos `N=5` días de silver y gold para absorber los eventos tardíos.
- `meta.cargas` registra qué archivo entró, cuándo y con cuántas filas, para no cargarlo dos veces.
- Pruebas:
  - cargar el mismo día dos veces da el mismo resultado;
  - la carga día a día da lo mismo que la carga completa;
  - un evento con 3 días de retraso corrige la deuda pasada;
  - un evento fuera de la ventana va a cuarentena con el motivo `fuera_de_ventana`.

### Sprint 5: Dataform y BigQuery (v0.5.0)
- `dataform/` con `workflow_settings.yaml`, `declare()` para bronze y las aserciones en el esquema `calidad`.
- Silver y gold con `type: "incremental"`, `uniqueKey`, `bigquery: {partitionBy: "fecha", clusterBy: ["id_mensajero"]}` y `when(incremental(), ...)` con la misma ventana de reproceso.
- El historial SCD tipo 2 se escribe como un `MERGE` en `operations`.
- `tests/test_dataform.py`: compila con Dataform, valida el dialecto BigQuery con sqlglot, transpila a DuckDB y comprueba que salen las mismas tablas y los mismos números.
- Una prueba verifica que las consultas sobre gold filtran por la columna de partición.
- `cargar_bigquery.py`: `bq load` a bronze, con bucket opcional y `--dia` para la carga incremental.
- Límite: sin cuenta de GCP, los bytes leídos solo se comprueban con `bq query --dry_run`; si no se ejecuta, queda documentado como no verificado.

### Sprint 6: BI y presentación (v1.0.0)
- `bi/` con Evidence leyendo los Parquet de gold.
- Página:
  - la deuda total como titular;
  - la deuda por mensajero en barras, con los tramos de antigüedad;
  - la línea del cierre de caja diario;
  - la tabla de pedidos perdidos.
- README en español e inglés: problema, arquitectura, cada regla en una frase, decisiones y cómo ejecutarlo.
- Capturas del panel en el README.
- Fuera del alcance: web de administración y login.

## Verificación de cada sprint

- `uv run pytest` en verde.
- Desde el sprint 3, `uv run python pipeline.py` imprime la deuda por mensajero y coincide con `verdad.json`.
- Desde el sprint 4, además, las pruebas de idempotencia y de llegada tardía.
- Desde el sprint 5, además, la equivalencia entre Dataform y DuckDB.

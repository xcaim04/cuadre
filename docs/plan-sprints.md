# Ruta Cobrada: plan de desarrollo por sprints

## Contexto

Este es el segundo proyecto de portafolio para la misma oferta de ingeniero de datos. La oferta pide BigQuery, las capas bronze/silver/gold, pytest, merge requests, una página de BI, Dataform y Claude Code. La prueba piloto se supera si el número cuadra y cada regla se explica en una frase.

Ruta Cobrada concilia el efectivo de una mensajería que cobra contra entrega. El número piloto es este:

> deuda del mensajero = cobrado − liquidado − devoluciones aprobadas

Debe cuadrar al centavo con la verdad que guarda el generador. El proyecto cubre lo que La Ceiba (`/home/xcaim/workspace/la-ceiba-data`) no enseña:

- cargas incrementales;
- datos que llegan tarde;
- SCD tipo 2;
- particiones y clustering en BigQuery;
- contratos de esquema.

## Lo que se hace al aprobar este plan

Solo el **sprint 0**. Cada sprint siguiente se hace cuando Carlos lo pida.

1. Crear el repo nuevo en `/home/xcaim/workspace/ruta-cobrada` (`git init`, rama `main` y rama `staging`), separado de La Ceiba.
2. Guardar este plan como `docs/plan-sprints.md` dentro del repo.
3. Montar el esqueleto: `pyproject.toml` con uv (duckdb y pytest; sqlglot en dev), `.gitignore`, un README corto en español y un test vacío que pase.
4. Hacer el primer commit en `staging`, con la línea Co-Authored-By.
5. No tocar GitHub: crear el repo remoto, hacer push o abrir PRs necesita el sí expreso de Carlos para cada acción.

## Forma de trabajo (igual que en La Ceiba)

- **Ramas y MRs:** una rama por sprint (`sprint-N-tema`), con PR hacia `staging`. Al cerrar el sprint, `staging` pasa a `main` y se etiqueta la versión.
- **Definición de hecho de cada sprint:** `uv run pytest` en verde, cada regla nueva con su frase en el README y su prueba, y el número piloto cuadrando con la verdad del generador.
- **Duración:** una semana de referencia por sprint.

## Sprints

### Sprint 0: esqueleto (v0.0.1)
- **Contenido:** repo, uv, plan en `docs/` y un workflow de GitHub Actions que corre pytest en cada PR, para que los MRs tengan CI visible.
- **Hecho cuando:** pytest pasa en local.

### Sprint 1: generador sintético y bronze (v0.1.0)
- **`generar/generar_datos.py`:** genera las 4 fuentes con semilla fija, 8 mensajeros y unos 60 días. Se basa en el patrón de `la-ceiba-data/generar/generar_datos.py`.
  - `pedidos/AAAA-MM-DD.csv`: pedidos diarios, con ediciones posteriores de importe y dirección.
  - `eventos/AAAA-MM-DD.jsonl`: eventos de la mensajería, con duplicados, desorden y un 5 % que llega de 1 a 4 días tarde.
  - `liquidaciones.csv`: la planilla del cajero, con alias del mensajero escritos de varias formas y pagos parciales.
  - `extracto_banco.csv`: los depósitos, que agrupan varios días.
  - `verdad.json`: la deuda real por mensajero y día. El pipeline nunca la lee; solo la usan las pruebas.
- **`sql/bronze/*.sql`:** todo como texto, más `_archivo_origen` y `_cargado_en`, igual que en La Ceiba.
- **Contrato de eventos:** `contratos/evento.json`, con las columnas y tipos esperados. Un campo desconocido se registra en `bronze.rechazos` en lugar de romper la carga en silencio.
- **Pruebas:** el generador es determinista y el contrato rechaza un evento malformado.

### Sprint 2: reglas de silver (v0.2.0)
Cada regla tiene su frase en el README y su prueba en pytest.
- **Duplicados:** un evento repetido con el mismo `id_evento` cuenta una vez.
- **Estado vigente:** el estado del pedido sale del evento con mayor `ocurrido_en`, no del último que llegó.
- **SCD tipo 2:** `silver.pedidos_historial` guarda cada versión del pedido con `valido_desde` y `valido_hasta`. El importe cobrable es el vigente en el momento de la entrega.
- **Alias de mensajeros:** se normalizan reutilizando la idea de `normalizar` de `la-ceiba-data/dataform/includes/texto.js` y de `sql/silver/01_maestros.sql`. El seed vive en `seeds/alias_mensajeros.csv`.
- **Cuarentena:** una entrega sin cobro registrado, o un cobro sin entrega, va a `silver.cuarentena` con su motivo; nunca se cuenta como cero.

### Sprint 3: gold y calidad (v0.3.0)
- **`gold.deuda_mensajero_dia`:** la deuda acumulada por mensajero y día, con su antigüedad en tramos de 0–2, 3–7 y más de 7 días.
- **`gold.cierre_caja`:** por día, lo vendido frente a lo cobrado, lo liquidado y lo depositado.
- **`gold.pedidos_perdidos`:** los pedidos que caen en cuarentena después de N días.
- **`sql/calidad/*.sql`:** convención de La Ceiba, donde cero filas significa que pasa. Unas 10 pruebas:
  - claves únicas;
  - importes positivos;
  - historial SCD sin solapes ni huecos;
  - la deuda cuadra con silver;
  - el cierre cuadra (vendido = cobrado + pendiente + devuelto);
  - la cuarentena queda por debajo del umbral;
  - nada de lo depositado supera lo liquidado.
- **`pipeline.py`:** si falla alguna prueba de calidad, no publica gold, igual que `recalcular()` en `la-ceiba-data/app/datos.py`.
- **Prueba clave:** `gold.deuda_mensajero_dia` es igual a `verdad.json`, centavo a centavo.

### Sprint 4: carga incremental y datos tardíos (v0.4.0)
- **Lotes diarios:** `pipeline.py --dia AAAA-MM-DD` procesa solo los archivos nuevos de ese día.
- **Escritura idempotente:** usa `MERGE` o `INSERT OR REPLACE` de DuckDB con clave única.
- **Ventana de reproceso:** cada carga vuelve a calcular los últimos `N=5` días de silver y gold, para absorber los eventos que llegan tarde.
- **Registro de cargas:** `meta.cargas` guarda qué archivo entró, cuándo y con cuántas filas, para no cargar dos veces.
- **Pruebas:**
  - cargar el mismo día dos veces da el mismo resultado;
  - una carga diaria da lo mismo que una completa;
  - un evento que llega con 3 días de retraso corrige la deuda pasada;
  - un evento que llega fuera de la ventana va a cuarentena con el motivo `fuera_de_ventana`.

### Sprint 5: Dataform y BigQuery (v0.5.0)
- **Modelos:** `dataform/` sigue la estructura de La Ceiba (`workflow_settings.yaml`, `declare()` en bronze y las aserciones en `calidad`).
- **Incrementales:** silver y gold usan `type: "incremental"` con `uniqueKey`, `bigquery: {partitionBy: "fecha", clusterBy: ["id_mensajero"]}` y un `when(incremental(), ...)` con la misma ventana de reproceso.
- **SCD tipo 2:** el historial en Dataform se escribe como un MERGE en `operations`.
- **`tests/test_dataform.py`:** copia el patrón de `la-ceiba-data/tests/test_dataform.py`. Compila con Dataform, valida el dialecto con sqlglot, transpila a DuckDB y comprueba que salen las mismas tablas y los mismos números.
- **Partición:** una prueba nueva verifica que las consultas de gold filtran por la columna de partición.
- **`cargar_bigquery.py`:** se adapta desde La Ceiba (bq load a bronze, con bucket opcional) y añade `--dia` para la carga incremental.
- **Límite honesto:** sin cuenta de GCP, el gasto en bytes leídos solo se comprueba con `bq query --dry_run` si Carlos la conecta. Si no, queda documentado como no verificado.

### Sprint 6: BI y presentación (v1.0.0)
- **`bi/`:** Evidence con las mismas versiones fijadas que La Ceiba (40.1.8, duckdb 2.0.1 y typescript 5.4.2). Lee los Parquet de gold.
- **Página:**
  - la deuda total como titular;
  - la deuda por mensajero en barras, con los tramos de antigüedad;
  - la línea del cierre de caja diario;
  - la tabla de pedidos perdidos.
- **Exportación:** se exportan los Parquet de gold, como en `app/datos.py` de La Ceiba.
- **README bilingüe:** se escribe en español y en inglés. Explica el problema, la arquitectura, cada regla en una frase, las decisiones tomadas y cómo ejecutar el proyecto.
- **Capturas:** se toman con el script de Playwright que ya se usó en La Ceiba.
- **Fuera del alcance:** sin web de administración ni login, porque eso ya lo demuestra La Ceiba.

## Archivos clave del repo nuevo

`generar/generar_datos.py` · `contratos/evento.json` · `sql/{bronze,silver,gold,calidad}/` · `pipeline.py` · `seeds/alias_mensajeros.csv` · `dataform/` · `cargar_bigquery.py` · `bi/` · `tests/test_{generador,silver,gold,incremental,dataform}.py` · `docs/plan-sprints.md`

## Verificación

- **Sprint 0:** `cd /home/xcaim/workspace/ruta-cobrada && uv run pytest` pasa, `git log` muestra el commit en `staging` y `docs/plan-sprints.md` existe.
- **Sprints siguientes:** en cada uno, pytest en verde y `uv run python pipeline.py` imprime la deuda por mensajero, que coincide con `verdad.json`.
- **Desde el sprint 4:** además, las pruebas de idempotencia y de llegada tardía.
- **Desde el sprint 5:** además, la equivalencia entre Dataform y DuckDB.

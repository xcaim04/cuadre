-- tabla: silver.eventos_revisados
-- clave: id_evento
-- Reglas de eventos:
-- 1. Un evento repetido con el mismo id_evento cuenta una vez: vale la primera copia que llegó.
-- 2. Un evento que llega más de {{ventana}} días después de ocurrir no reabre días cerrados: va a cuarentena.
-- 3. Un evento que no se puede usar va a cuarentena con su motivo; nunca cuenta como cero.
-- Incremental: se revisan de nuevo los eventos llegados desde {{desde}}, porque una entrega tardía puede
-- resolver una devolución que antes no tenía entrega.
WITH unicos AS (
    SELECT *, CAST(split_part(_archivo_origen, '.', 1) AS DATE) AS fecha_llegada FROM bronze.eventos
    QUALIFY row_number() OVER (PARTITION BY id_evento ORDER BY _archivo_origen, _linea) = 1
),
tipados AS (
    SELECT id_evento, id_pedido, id_mensajero, tipo, try_cast(ocurrido_en AS TIMESTAMP) AS ocurrido_en,
           try_cast(importe AS DECIMAL(12, 2)) AS importe, importe AS importe_texto, _archivo_origen, fecha_llegada
    FROM unicos
),
revisados AS (
    SELECT *, CASE
            WHEN tipo NOT IN ('entrega', 'rechazo', 'devolucion') THEN 'tipo_desconocido'
            WHEN ocurrido_en IS NULL OR (importe_texto IS NOT NULL AND importe IS NULL) THEN 'dato_invalido'
            WHEN CAST(ocurrido_en AS DATE) < fecha_llegada - {{ventana}} THEN 'fuera_de_ventana'
            WHEN id_mensajero NOT IN (SELECT id_mensajero FROM silver.alias_mensajeros) THEN 'mensajero_desconocido'
            WHEN id_pedido NOT IN (SELECT id_pedido FROM silver.pedidos_historial) THEN 'pedido_desconocido'
            WHEN tipo = 'entrega' AND importe IS NULL THEN 'entrega_sin_cobro'
            WHEN tipo = 'devolucion' AND importe IS NULL THEN 'devolucion_sin_importe'
            WHEN importe <= 0 THEN 'importe_no_positivo'
        END AS motivo
    FROM tipados
)
SELECT r.* EXCLUDE (importe_texto, motivo),
       CASE WHEN r.motivo IS NULL AND r.tipo = 'devolucion' AND NOT EXISTS (
                SELECT 1 FROM revisados e WHERE e.id_pedido = r.id_pedido AND e.tipo = 'entrega' AND e.motivo IS NULL)
            THEN 'devolucion_sin_entrega' ELSE r.motivo END AS motivo
FROM revisados r
WHERE r.fecha_llegada >= DATE '{{desde}}';

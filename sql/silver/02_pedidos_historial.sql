-- tabla: silver.pedidos_historial
-- clave: id_pedido
-- Regla (SCD tipo 2): cada versión de un pedido vale desde su actualizado_en hasta la versión siguiente; la última sigue vigente.
-- Incremental: se reescribe el historial entero de cada pedido con versiones llegadas desde {{desde}}.
-- Los pedidos vienen del sistema de la tienda: un tipo inválido detiene el pipeline en lugar de esconderse en cuarentena.
WITH versiones AS (
    SELECT DISTINCT id_pedido, CAST(actualizado_en AS TIMESTAMP) AS valido_desde, id_mensajero, cliente, direccion,
           CAST(importe AS DECIMAL(12, 2)) AS importe
    FROM bronze.pedidos
),
tocados AS (
    SELECT DISTINCT id_pedido FROM bronze.pedidos
    WHERE CAST(split_part(_archivo_origen, '.', 1) AS DATE) >= DATE '{{desde}}'
)
SELECT *, lead(valido_desde) OVER (PARTITION BY id_pedido ORDER BY valido_desde) AS valido_hasta
FROM versiones
WHERE id_pedido IN (SELECT id_pedido FROM tocados);

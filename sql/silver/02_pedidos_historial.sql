-- Regla (SCD tipo 2): cada versión de un pedido vale desde su actualizado_en hasta la versión siguiente; la última sigue vigente.
-- Los pedidos vienen del sistema de la tienda: un tipo inválido detiene el pipeline en lugar de esconderse en cuarentena.
CREATE OR REPLACE TABLE silver.pedidos_historial AS
WITH versiones AS (
    SELECT DISTINCT id_pedido, CAST(actualizado_en AS TIMESTAMP) AS valido_desde, id_mensajero, cliente, direccion,
           CAST(importe AS DECIMAL(12, 2)) AS importe
    FROM bronze.pedidos
)
SELECT *, lead(valido_desde) OVER (PARTITION BY id_pedido ORDER BY valido_desde) AS valido_hasta
FROM versiones;

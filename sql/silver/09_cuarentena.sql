-- tabla: silver.cuarentena
-- Regla: lo que no se puede usar queda en cuarentena con su motivo; nunca cuenta como cero.
SELECT 'eventos' AS origen, id_evento AS referencia, id_pedido, id_mensajero, CAST(ocurrido_en AS DATE) AS fecha,
       importe, motivo
FROM silver.eventos_revisados WHERE motivo IS NOT NULL
UNION ALL
SELECT 'liquidaciones', alias_original, CAST(NULL AS VARCHAR), id_mensajero, fecha, importe, motivo
FROM silver.liquidaciones_revisadas WHERE motivo IS NOT NULL;

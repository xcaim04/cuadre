-- Todo importe que mueve dinero es mayor que cero.
SELECT 'eventos' AS tabla, id_evento AS referencia FROM silver.eventos
WHERE tipo IN ('entrega', 'devolucion') AND (importe IS NULL OR importe <= 0)
UNION ALL SELECT 'liquidaciones', alias_original FROM silver.liquidaciones WHERE importe <= 0
UNION ALL SELECT 'depositos', referencia FROM silver.depositos WHERE importe <= 0
UNION ALL SELECT 'pedidos_historial', id_pedido FROM silver.pedidos_historial WHERE importe <= 0;

-- Dos versiones de un pedido no pueden empezar a la vez: no se sabría cuál vale.
SELECT id_pedido, valido_desde FROM silver.pedidos_historial GROUP BY ALL HAVING count(*) > 1;

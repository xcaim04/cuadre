-- Cada pedido aparece una sola vez en silver.pedidos.
SELECT id_pedido FROM silver.pedidos GROUP BY id_pedido HAVING count(*) > 1;

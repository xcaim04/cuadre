-- No se devuelve a un cliente más de lo que se le cobró.
SELECT id_pedido FROM silver.eventos
GROUP BY id_pedido
HAVING sum(importe) FILTER (tipo = 'devolucion') > coalesce(sum(importe) FILTER (tipo = 'entrega'), 0);

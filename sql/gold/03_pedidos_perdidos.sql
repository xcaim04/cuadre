-- tabla: gold.pedidos_perdidos
-- Pedido perdido: sigue sin entrega ni rechazo válidos más de 3 días después de creado.
-- Si tiene algún evento en cuarentena, se muestra el motivo para saber por dónde buscar.
WITH corte AS (SELECT max(CAST(ocurrido_en AS DATE)) AS fecha FROM silver.eventos),
creados AS (SELECT id_pedido, min(valido_desde) AS creado_en FROM silver.pedidos_historial GROUP BY id_pedido),
motivos AS (
    SELECT id_pedido, array_to_string(list_sort(list(DISTINCT motivo)), ', ') AS motivo_cuarentena
    FROM silver.cuarentena WHERE id_pedido IS NOT NULL GROUP BY id_pedido
)
SELECT p.id_pedido, p.id_mensajero, p.cliente, p.importe_actual, c.creado_en,
       corte.fecha - CAST(c.creado_en AS DATE) AS dias_sin_cierre, m.motivo_cuarentena
FROM silver.pedidos p
JOIN creados c USING (id_pedido)
CROSS JOIN corte
LEFT JOIN motivos m USING (id_pedido)
WHERE p.estado = 'pendiente' AND corte.fecha - CAST(c.creado_en AS DATE) > 3;

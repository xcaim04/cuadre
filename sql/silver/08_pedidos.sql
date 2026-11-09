-- tabla: silver.pedidos
-- Reglas de pedidos (foto del estado actual, se reconstruye entera):
-- 1. El estado de un pedido es el de su evento válido con mayor ocurrido_en, no el del último que llegó.
-- 2. El importe cobrable es el de la versión del pedido vigente en el momento de la entrega.
WITH ultimo AS (
    SELECT id_pedido, tipo FROM silver.eventos
    QUALIFY row_number() OVER (PARTITION BY id_pedido ORDER BY ocurrido_en DESC, id_evento DESC) = 1
),
entrega AS (
    SELECT id_pedido, ocurrido_en AS entregado_en, importe AS importe_cobrado FROM silver.eventos
    WHERE tipo = 'entrega'
    QUALIFY row_number() OVER (PARTITION BY id_pedido ORDER BY ocurrido_en DESC, id_evento DESC) = 1
)
SELECT h.id_pedido, h.id_mensajero, h.cliente, h.direccion, h.importe AS importe_actual,
       CASE u.tipo WHEN 'entrega' THEN 'entregado' WHEN 'rechazo' THEN 'rechazado'
                   WHEN 'devolucion' THEN 'devuelto' ELSE 'pendiente' END AS estado,
       e.entregado_en, e.importe_cobrado, v.importe AS importe_cobrable
FROM silver.pedidos_historial h
LEFT JOIN ultimo u USING (id_pedido)
LEFT JOIN entrega e USING (id_pedido)
LEFT JOIN silver.pedidos_historial v
       ON v.id_pedido = h.id_pedido AND v.valido_desde <= e.entregado_en
      AND (v.valido_hasta IS NULL OR e.entregado_en < v.valido_hasta)
WHERE h.valido_hasta IS NULL;

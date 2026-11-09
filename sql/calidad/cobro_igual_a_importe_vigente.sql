-- Lo que el mensajero cobró es el importe de la versión del pedido vigente al entregar.
SELECT id_pedido, importe_cobrado, importe_cobrable FROM silver.pedidos
WHERE entregado_en IS NOT NULL AND importe_cobrable IS DISTINCT FROM importe_cobrado;

-- El cierre de caja no pierde dinero: sus totales son los de silver.
WITH cierre AS (SELECT sum(cobrado) AS c, sum(devuelto) AS d, sum(liquidado) AS l, sum(depositado) AS p FROM gold.cierre_caja)
SELECT * FROM cierre
WHERE c <> (SELECT coalesce(sum(importe), 0) FROM silver.eventos WHERE tipo = 'entrega')
   OR d <> (SELECT coalesce(sum(importe), 0) FROM silver.eventos WHERE tipo = 'devolucion')
   OR l <> (SELECT coalesce(sum(importe), 0) FROM silver.liquidaciones)
   OR p <> (SELECT coalesce(sum(importe), 0) FROM silver.depositos);

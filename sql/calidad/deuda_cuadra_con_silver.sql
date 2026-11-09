-- La deuda final de gold es la suma directa de silver: cobrado − devuelto − liquidado.
WITH silver AS (
    SELECT id_mensajero, sum(importe) AS deuda FROM (
        SELECT id_mensajero, CASE tipo WHEN 'entrega' THEN importe WHEN 'devolucion' THEN -importe ELSE 0 END AS importe
        FROM silver.eventos
        UNION ALL SELECT id_mensajero, -importe FROM silver.liquidaciones
    ) GROUP BY id_mensajero
),
gold AS (SELECT id_mensajero, deuda FROM gold.deuda_mensajero_dia QUALIFY fecha = max(fecha) OVER ())
SELECT * FROM silver FULL JOIN gold USING (id_mensajero)
WHERE coalesce(silver.deuda, 0) <> coalesce(gold.deuda, 0);

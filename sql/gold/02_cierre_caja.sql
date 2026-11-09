-- Cierre de caja diario: dónde está el efectivo cobrado.
-- Lo cobrado menos lo devuelto está en manos de los mensajeros, en la oficina o depositado en el banco.
CREATE OR REPLACE TABLE gold.cierre_caja AS
WITH dias AS (
    SELECT fecha, sum(cobrado) AS cobrado, sum(devuelto) AS devuelto, sum(liquidado) AS liquidado,
           sum(deuda) AS en_mensajeros
    FROM gold.deuda_mensajero_dia GROUP BY fecha
),
depositos AS (SELECT fecha, sum(importe) AS depositado FROM silver.depositos GROUP BY fecha)
SELECT d.fecha, d.cobrado, d.devuelto, d.liquidado, coalesce(p.depositado, 0) AS depositado, d.en_mensajeros,
       sum(d.liquidado - coalesce(p.depositado, 0)) OVER w AS en_oficina,
       sum(coalesce(p.depositado, 0)) OVER w AS depositado_acum
FROM dias d LEFT JOIN depositos p USING (fecha)
WINDOW w AS (ORDER BY d.fecha);

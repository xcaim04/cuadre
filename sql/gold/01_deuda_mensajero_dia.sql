-- tabla: gold.deuda_mensajero_dia
-- clave: fecha
-- Deuda de cada mensajero al cierre de cada día: cobrado − devuelto − liquidado, acumulado.
-- Antigüedad (FIFO): lo que el mensajero devuelve o liquida paga primero sus cobros más viejos.
-- Incremental: se reescriben los días desde {{desde}}; los anteriores ya no cambian, porque un evento
-- con más días de atraso que la ventana va a cuarentena.
WITH movimientos AS (
    SELECT id_mensajero, CAST(ocurrido_en AS DATE) AS fecha,
           CASE WHEN tipo = 'entrega' THEN importe ELSE 0 END AS cobrado,
           CASE WHEN tipo = 'devolucion' THEN importe ELSE 0 END AS devuelto,
           0 AS liquidado
    FROM silver.eventos
    UNION ALL
    SELECT id_mensajero, fecha, 0, 0, importe FROM silver.liquidaciones
),
calendario AS (
    SELECT CAST(dia AS DATE) AS fecha, id_mensajero
    FROM generate_series((SELECT min(fecha) FROM movimientos)::TIMESTAMP,
                         (SELECT max(fecha) FROM movimientos)::TIMESTAMP, INTERVAL 1 DAY) AS t(dia)
    CROSS JOIN (SELECT DISTINCT id_mensajero FROM silver.alias_mensajeros)
),
diario AS (
    SELECT c.fecha, c.id_mensajero, coalesce(sum(m.cobrado), 0) AS cobrado,
           coalesce(sum(m.devuelto), 0) AS devuelto, coalesce(sum(m.liquidado), 0) AS liquidado
    FROM calendario c LEFT JOIN movimientos m USING (fecha, id_mensajero)
    GROUP BY ALL
),
acumulado AS (
    SELECT *, sum(cobrado) OVER w AS cobrado_acum, sum(devuelto + liquidado) OVER w AS pagado_acum
    FROM diario WINDOW w AS (PARTITION BY id_mensajero ORDER BY fecha)
),
tramos AS (
    -- Parte de lo cobrado el día d que sigue sin pagar al cierre del día del corte.
    SELECT corte.fecha, corte.id_mensajero, corte.fecha - d.fecha AS dias,
           greatest(0, least(d.cobrado, d.cobrado_acum - corte.pagado_acum)) AS sin_pagar
    FROM acumulado corte
    JOIN acumulado d ON d.id_mensajero = corte.id_mensajero AND d.fecha <= corte.fecha
    WHERE corte.fecha >= DATE '{{desde}}'
)
SELECT a.fecha, a.id_mensajero, a.cobrado, a.devuelto, a.liquidado,
       a.cobrado_acum - a.pagado_acum AS deuda,
       coalesce(sum(t.sin_pagar) FILTER (t.dias <= 2), 0) AS deuda_0_2,
       coalesce(sum(t.sin_pagar) FILTER (t.dias BETWEEN 3 AND 7), 0) AS deuda_3_7,
       coalesce(sum(t.sin_pagar) FILTER (t.dias > 7), 0) AS deuda_mas_7
FROM acumulado a
JOIN tramos t USING (fecha, id_mensajero)
WHERE a.fecha >= DATE '{{desde}}'
GROUP BY ALL;

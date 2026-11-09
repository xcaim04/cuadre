-- Cada evento aparece una sola vez en silver.
SELECT id_evento FROM silver.eventos GROUP BY id_evento HAVING count(*) > 1;

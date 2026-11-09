-- tabla: silver.eventos
-- Los eventos que se pueden usar.
SELECT * EXCLUDE (motivo) FROM silver.eventos_revisados WHERE motivo IS NULL;

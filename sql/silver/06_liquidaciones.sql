-- tabla: silver.liquidaciones
-- Las liquidaciones que se pueden usar.
SELECT * EXCLUDE (motivo) FROM silver.liquidaciones_revisadas WHERE motivo IS NULL;

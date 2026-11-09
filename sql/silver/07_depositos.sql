-- tabla: silver.depositos
-- clave: _archivo_origen
-- El extracto viene del banco: un tipo inválido detiene el pipeline.
-- Incremental: se reescriben los extractos llegados desde {{desde}}.
SELECT CAST(fecha AS DATE) AS fecha, referencia, CAST(importe AS DECIMAL(12, 2)) AS importe, _archivo_origen
FROM bronze.extracto_banco
WHERE CAST(split_part(_archivo_origen, '.', 1) AS DATE) >= DATE '{{desde}}';

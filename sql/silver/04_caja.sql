-- Regla: una liquidación se asigna al mensajero por su alias normalizado; si el alias no está en el seed, va a cuarentena.
CREATE OR REPLACE TABLE silver.liquidaciones_revisadas AS
SELECT try_cast(l.fecha AS DATE) AS fecha, a.id_mensajero, l.mensajero AS alias_original,
       try_cast(l.importe AS DECIMAL(12, 2)) AS importe, l._archivo_origen,
       CASE WHEN a.id_mensajero IS NULL THEN 'mensajero_desconocido'
            WHEN try_cast(l.fecha AS DATE) IS NULL OR try_cast(l.importe AS DECIMAL(12, 2)) IS NULL THEN 'dato_invalido'
            WHEN try_cast(l.importe AS DECIMAL(12, 2)) <= 0 THEN 'importe_no_positivo'
       END AS motivo
FROM bronze.liquidaciones l
LEFT JOIN silver.alias_mensajeros a ON normalizar(l.mensajero) = a.alias;

CREATE OR REPLACE TABLE silver.liquidaciones AS
SELECT * EXCLUDE (motivo) FROM silver.liquidaciones_revisadas WHERE motivo IS NULL;

-- El extracto viene del banco: un tipo inválido detiene el pipeline.
CREATE OR REPLACE TABLE silver.depositos AS
SELECT CAST(fecha AS DATE) AS fecha, referencia, CAST(importe AS DECIMAL(12, 2)) AS importe
FROM bronze.extracto_banco;

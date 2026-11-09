-- tabla: silver.liquidaciones_revisadas
-- clave: _archivo_origen
-- Regla: una liquidación se asigna al mensajero por su alias normalizado; si el alias no está en el seed, va a cuarentena.
-- Incremental: se reescriben las planillas llegadas desde {{desde}}.
SELECT try_cast(l.fecha AS DATE) AS fecha, a.id_mensajero, l.mensajero AS alias_original,
       try_cast(l.importe AS DECIMAL(12, 2)) AS importe, l._archivo_origen,
       CASE WHEN a.id_mensajero IS NULL THEN 'mensajero_desconocido'
            WHEN try_cast(l.fecha AS DATE) IS NULL OR try_cast(l.importe AS DECIMAL(12, 2)) IS NULL THEN 'dato_invalido'
            WHEN try_cast(l.importe AS DECIMAL(12, 2)) <= 0 THEN 'importe_no_positivo'
       END AS motivo
FROM bronze.liquidaciones l
LEFT JOIN silver.alias_mensajeros a ON normalizar(l.mensajero) = a.alias
WHERE CAST(split_part(l._archivo_origen, '.', 1) AS DATE) >= DATE '{{desde}}';

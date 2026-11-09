-- Bronze: cada archivo se agrega tal cual llega, todo como texto, más de dónde y cuándo se cargó.
-- Una columna nueva en el archivo hace fallar el INSERT: un cambio de formato se ve, no se esconde.
CREATE TABLE IF NOT EXISTS bronze.{{fuente}} AS
SELECT *, '' AS _archivo_origen, current_timestamp AS _cargado_en FROM read_csv('{{archivo}}', all_varchar = true) LIMIT 0;

INSERT INTO bronze.{{fuente}} BY NAME
SELECT *, '{{nombre}}' AS _archivo_origen, current_timestamp AS _cargado_en FROM read_csv('{{archivo}}', all_varchar = true);

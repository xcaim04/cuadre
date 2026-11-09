-- Regla: un nombre de mensajero se compara sin mayúsculas, tildes ni espacios de más, y se traduce a su id con el seed de alias.
CREATE OR REPLACE MACRO normalizar(x) AS strip_accents(lower(trim(regexp_replace(x, '\s+', ' ', 'g'))));

CREATE OR REPLACE TABLE silver.alias_mensajeros AS
SELECT DISTINCT normalizar(alias) AS alias, id_mensajero
FROM read_csv('{{seeds}}/alias_mensajeros.csv', all_varchar = true);

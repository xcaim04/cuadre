-- tabla: silver.alias_mensajeros
-- Regla: un nombre de mensajero se traduce a su id con el seed de alias, comparado ya normalizado.
SELECT DISTINCT normalizar(alias) AS alias, id_mensajero
FROM read_csv('{{seeds}}/alias_mensajeros.csv', all_varchar = true);

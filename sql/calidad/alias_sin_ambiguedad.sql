-- Un alias normalizado lleva a un solo mensajero.
SELECT alias FROM silver.alias_mensajeros GROUP BY alias HAVING count(DISTINCT id_mensajero) > 1;

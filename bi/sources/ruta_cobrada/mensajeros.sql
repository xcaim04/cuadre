-- El nombre oficial de cada mensajero sale del seed de alias; los apodos (Yoyi, Yusle) no llevan espacio.
SELECT id_mensajero, min(alias) AS nombre FROM read_csv('../seeds/alias_mensajeros.csv') WHERE alias LIKE '% %' GROUP BY 1

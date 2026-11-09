-- Si más del 2 % de los eventos cae en cuarentena, algo cambió en la fuente y hay que mirarlo antes de publicar.
SELECT count(*) FILTER (motivo IS NOT NULL) AS en_cuarentena, count(*) AS eventos FROM silver.eventos_revisados
HAVING count(*) FILTER (motivo IS NOT NULL) > 0.02 * count(*);

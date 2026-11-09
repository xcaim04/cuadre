// Días que se recalculan en cada carga incremental; un evento más atrasado va a cuarentena. Igual que VENTANA en pipeline.py.
const VENTANA = 5;

// La misma normalización que la versión DuckDB: minúsculas, sin tildes y sin espacios repetidos.
function normalizar(columna) {
  return `LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(NORMALIZE(${columna}, NFD), r'\\pM', ''), r'\\s+', ' ')))`;
}

// Fecha del archivo de origen: "2026-09-01.jsonl" -> 2026-09-01.
function fecha_archivo(columna) {
  return `CAST(SUBSTR(${columna}, 1, 10) AS DATE)`;
}

module.exports = { VENTANA, normalizar, fecha_archivo };

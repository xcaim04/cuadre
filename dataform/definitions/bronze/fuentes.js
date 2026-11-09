// Bronze: cargar_bigquery.py carga cada archivo diario tal cual, todo como texto, con _archivo_origen y _cargado_en.
// Los eventos llegan ya revisados contra contratos/evento.json; lo que no lo cumple está en bronze.rechazos_contrato.
["pedidos", "eventos", "liquidaciones", "extracto_banco", "rechazos_contrato", "alias_mensajeros"]
  .forEach((name) => declare({ schema: "bronze", name }));

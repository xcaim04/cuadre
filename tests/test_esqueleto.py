"""Prueba mínima del sprint 0: el entorno arranca y DuckDB responde."""

import duckdb


def test_duckdb_responde():
    assert duckdb.connect().execute("SELECT 1").fetchone() == (1,)

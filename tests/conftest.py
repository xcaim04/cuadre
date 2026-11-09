import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "generar"))

from generar_datos import generar  # noqa: E402


@pytest.fixture(scope="session")
def raw(tmp_path_factory):
    """Los datos sintéticos completos, generados una vez por sesión de pruebas."""
    carpeta = tmp_path_factory.mktemp("raw")
    generar(carpeta)
    return carpeta

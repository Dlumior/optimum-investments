import pytest

from optimum.cleaning import build_processed
from optimum.io.excel import load_workbook


def pytest_configure(config):
    """Registra el marker `slow` (pruebas de integración con input.json; se ejecutan por defecto).

    Para omitirlas en una iteración rápida: `pytest -m "not slow"`.
    """
    config.addinivalue_line("markers", "slow: integración con input.json real (se ejecuta por defecto)")


@pytest.fixture(scope="session")
def raw():
    return load_workbook()


@pytest.fixture(scope="session")
def tables(raw):
    return build_processed(raw)

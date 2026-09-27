import pytest

from optimum.cleaning import build_processed
from optimum.io.excel import load_workbook


@pytest.fixture(scope="session")
def raw():
    return load_workbook()


@pytest.fixture(scope="session")
def tables(raw):
    return build_processed(raw)

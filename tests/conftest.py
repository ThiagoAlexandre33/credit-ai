"""Isola a persistência automática de métricas de toda a suíte."""

import pytest
from database import database
from automations import report_automation
from integrations import bcb_client


@pytest.fixture(autouse=True)
def banco_local_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "CAMINHO_BANCO", tmp_path / "aplicacao_teste.db")
    monkeypatch.setattr(report_automation, "PASTA_REPORTS", tmp_path / "reports")
    monkeypatch.setattr(bcb_client, "_cache", None)
    monkeypatch.setattr(bcb_client, "_cache_ate", 0.0)
    monkeypatch.setattr(bcb_client, "_cache_dia", None)

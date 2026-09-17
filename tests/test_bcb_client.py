"""Contrato BCB com transporte falso, sem depender da internet."""

from datetime import date, timedelta
import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from integrations import bcb_client as bcb
from database import database


@pytest.fixture
def transporte(monkeypatch):
    cliente = Mock()
    monkeypatch.setattr(bcb, "build_opener", Mock(return_value=cliente))
    return cliente


def resposta_http(conteudo, status=200):
    resposta = io.BytesIO(conteudo)
    resposta.status = status
    return resposta


def dados_validos():
    return [{"data": date.today().strftime("%d/%m/%Y"), "valor": "13.25"},
            {"data": (date.today() - timedelta(days=1)).strftime("%d/%m/%Y"), "valor": "12,50"}]


def test_valido_mais_recente_e_monitoramento(transporte):
    transporte.open.return_value = resposta_http(json.dumps(dados_validos()).encode())
    resultado = bcb.consultar_selic_recente()
    assert resultado["valor_percentual_ano"] == 13.25
    assert resultado["data_referencia"] == date.today().strftime("%d/%m/%Y")
    assert resultado["serie_sgs"] == 1178
    assert resultado["origem"] == "api"
    url = transporte.open.call_args.args[0].full_url
    assert urlsplit(url).netloc == "api.bcb.gov.br"
    assert parse_qs(urlsplit(url).query)["dataFinal"] == [date.today().strftime("%d/%m/%Y")]
    assert transporte.open.call_args.kwargs["timeout"] == bcb.TIMEOUT
    metrica = database.listar_metricas()[0]
    assert metrica["operacao"] == "external_api"
    assert metrica["ferramenta"] == "bcb_selic"
    assert metrica["status"] == "sucesso"
    assert "13.25" not in json.dumps(metrica)


@pytest.mark.parametrize("conteudo", [b"[]", b"{}", b"invalido", b'[{}]',
    b'[{"data":"31/02/2026","valor":"10"}]',
    b'[{"data":"01/01/1900","valor":"10"}]',
    json.dumps([{"data": date.today().strftime("%d/%m/%Y"), "valor": "NaN"}]).encode(),
    json.dumps([{"data": date.today().strftime("%d/%m/%Y"), "valor": True}]).encode(),
    json.dumps([{"data": date.today().strftime("%d/%m/%Y"), "valor": "abc"}]).encode(),
    json.dumps([{"data": (date.today() + timedelta(days=1)).strftime("%d/%m/%Y"), "valor": "10"}]).encode(),
])
def test_resposta_invalida(transporte, conteudo):
    transporte.open.return_value = resposta_http(conteudo)
    with pytest.raises(bcb.BCBRespostaInvalida):
        bcb.consultar_selic_recente()
    assert database.listar_metricas()[0]["status"] == "erro"
    assert bcb._cache is None


@pytest.mark.parametrize("erro", [TimeoutError(), URLError("offline"), HTTPError("url", 503, "erro", {}, None)])
def test_indisponivel(transporte, erro):
    transporte.open.side_effect = erro
    with pytest.raises(bcb.BCBIndisponivel):
        bcb.consultar_selic_recente()


def test_http_nao_200(transporte):
    transporte.open.return_value = resposta_http(b"[]", 204)
    with pytest.raises(bcb.BCBIndisponivel):
        bcb.consultar_selic_recente()


@pytest.mark.parametrize("url", ["http://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados",
    "https://malicioso.example/dados/serie/bcdata.sgs.1178/dados", "http://127.0.0.1/",
    "https://api.bcb.gov.br@malicioso.example/", "file:///privado", "https://api.bcb.gov.br/outro"])
def test_endpoint_arbitrario_rejeitado(url):
    with pytest.raises(ValueError):
        bcb._validar_endpoint(url)


def test_url_nao_e_parametro():
    with pytest.raises(TypeError):
        bcb.consultar_selic_recente(url="http://127.0.0.1")
    assert bcb._SemRedirecionamento().redirect_request(None, None, 302, "", {}, "http://127.0.0.1") is None


def test_cache_copia_ttl_e_sem_fallback(transporte, monkeypatch):
    relogio = Mock(return_value=100)
    monkeypatch.setattr(bcb.time, "monotonic", relogio)
    transporte.open.return_value = resposta_http(json.dumps(dados_validos()).encode())
    primeiro = bcb.consultar_selic_recente()
    primeiro["valor_percentual_ano"] = 999
    segundo = bcb.consultar_selic_recente()
    assert segundo["valor_percentual_ano"] == 13.25
    assert segundo["origem"] == "cache"
    assert transporte.open.call_count == 1
    relogio.return_value = 100 + bcb.CACHE_TTL + 1
    transporte.open.side_effect = TimeoutError()
    with pytest.raises(bcb.BCBIndisponivel):
        bcb.consultar_selic_recente()
    assert transporte.open.call_count == 2

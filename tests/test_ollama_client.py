"""Transporte Ollama testado sem rede ou modelo instalado."""

import io
import json
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from agent import ollama_client as cliente


def test_requisicao_local_estruturada():
    dados = {"intencao": "outra", "argumentos": {}}
    envelope = {"done": True, "message": {"content": json.dumps(dados)}}
    transporte = Mock()
    transporte.open.return_value = io.BytesIO(json.dumps(envelope).encode())
    with patch.object(cliente, "build_opener", return_value=transporte):
        assert cliente.consultar_modelo([{"role": "user", "content": "Olá"}], {"type": "object"}) == dados
    chamada = transporte.open.call_args
    requisicao = chamada.args[0]
    corpo = json.loads(requisicao.data)
    assert requisicao.full_url == "http://127.0.0.1:11434/api/chat"
    assert corpo["model"] == "llama3.2:3b"
    assert corpo["stream"] is False
    assert corpo["format"] == {"type": "object"}
    assert chamada.kwargs["timeout"] == cliente.TIMEOUT


@pytest.mark.parametrize("erro", [URLError("offline"), TimeoutError(), HTTPError("local", 404, "modelo ausente", {}, None)])
def test_indisponibilidade(erro):
    transporte = Mock()
    transporte.open.side_effect = erro
    with patch.object(cliente, "build_opener", return_value=transporte):
        with pytest.raises(cliente.OllamaIndisponivel):
            cliente.consultar_modelo([], {})


@pytest.mark.parametrize("conteudo", [b"nao json", b"{}", b"[]",
    b'{"done":false}', b'{"done":true,"message":{"content":"texto livre"}}',
    b'{"done":true,"message":{"content":5}}'])
def test_envelope_invalido(conteudo):
    transporte = Mock()
    transporte.open.return_value = io.BytesIO(conteudo)
    with patch.object(cliente, "build_opener", return_value=transporte):
        with pytest.raises(cliente.RespostaInvalida):
            cliente.consultar_modelo([], {})

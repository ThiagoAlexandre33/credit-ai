"""Transporte HTTP exclusivamente local para o Ollama, sem dependências extras."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from monitoring.metrics import medir_operacao

MODELO = "llama3.2:3b"
URL_CHAT = "http://127.0.0.1:11434/api/chat"
TIMEOUT = 120


class OllamaIndisponivel(Exception):
    """O servidor ou modelo local não está disponível."""


class RespostaInvalida(Exception):
    """O servidor retornou uma resposta que não pode ser interpretada."""


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@medir_operacao("ollama", modelo=MODELO)
def consultar_modelo(mensagens, esquema):
    """Envia mensagens e retorna somente o conteúdo JSON do modelo.

    Proxies e redirecionamentos são desativados para manter a chamada local.
    Não baixa modelos nem tenta serviços alternativos em caso de falha.
    """
    corpo = {
        "model": MODELO,
        "messages": mensagens,
        "stream": False,
        "format": esquema,
        "options": {"temperature": 0, "num_predict": 256},
    }
    requisicao = Request(
        URL_CHAT, data=json.dumps(corpo, allow_nan=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        cliente = build_opener(ProxyHandler({}), _SemRedirecionamento())
        with cliente.open(requisicao, timeout=TIMEOUT) as resposta:
            envelope = json.loads(resposta.read().decode("utf-8"))
        if not isinstance(envelope, dict) or envelope.get("done") is not True:
            raise RespostaInvalida()
        conteudo = envelope["message"]["content"]
        if not isinstance(conteudo, str):
            raise RespostaInvalida()
        return json.loads(conteudo)
    except (HTTPError, URLError, TimeoutError, OSError) as erro:
        raise OllamaIndisponivel() from erro
    except (ValueError, KeyError, TypeError, UnicodeError) as erro:
        raise RespostaInvalida() from erro

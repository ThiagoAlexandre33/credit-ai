"""Consulta pública fixa à série SGS 1178, sem URLs fornecidas pelo usuário."""

from datetime import date, datetime, timedelta
from http.client import HTTPException
import json
import math
import re
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from monitoring.metrics import medir_operacao

URL_BASE = "https://api.bcb.gov.br"
SERIE_SGS = 1178
TIMEOUT = 15
DIAS_CONSULTA = 30
CACHE_TTL = 3600
_cache = None
_cache_ate = 0.0
_cache_dia = None
_lock = Lock()


class BCBIndisponivel(Exception):
    """Falha de comunicação com o BCB, sem expor detalhes ao usuário."""


class BCBRespostaInvalida(Exception):
    """Resposta vazia ou fora do contrato esperado."""


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validar_endpoint(url):
    partes = urlsplit(url)
    if (partes.scheme != "https" or partes.netloc != "api.bcb.gov.br"
            or partes.path != "/dados/serie/bcdata.sgs.1178/dados" or partes.fragment):
        raise ValueError("Endpoint não permitido.")


def _validar_registros(registros, inicio, fim):
    if not isinstance(registros, list) or not registros:
        raise BCBRespostaInvalida()
    validados = []
    for registro in registros:
        if not isinstance(registro, dict) or not {"data", "valor"} <= set(registro):
            raise BCBRespostaInvalida()
        data_texto, valor = registro["data"], registro["valor"]
        if not isinstance(data_texto, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", data_texto):
            raise BCBRespostaInvalida()
        if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
            raise BCBRespostaInvalida()
        try:
            data_registro = datetime.strptime(data_texto, "%d/%m/%Y").date()
            valor = float(valor.replace(",", ".")) if isinstance(valor, str) else float(valor)
        except (ValueError, OverflowError):
            raise BCBRespostaInvalida() from None
        if not inicio <= data_registro <= fim or not math.isfinite(valor) or valor < 0:
            raise BCBRespostaInvalida()
        validados.append((data_registro, valor))
    data_registro, valor = max(validados, key=lambda item: item[0])
    return {"indicador": "selic_anualizada_base_252", "serie_sgs": SERIE_SGS,
            "valor_percentual_ano": valor, "data_referencia": data_registro.strftime("%d/%m/%Y"),
            "fonte": "Banco Central do Brasil", "status": "sucesso"}


@medir_operacao("external_api", ferramenta="bcb_selic")
def _consultar_api():
    fim = date.today()
    inicio = fim - timedelta(days=DIAS_CONSULTA)
    url = URL_BASE + "/dados/serie/bcdata.sgs.1178/dados?" + urlencode({
        "formato": "json", "dataInicial": inicio.strftime("%d/%m/%Y"), "dataFinal": fim.strftime("%d/%m/%Y")})
    _validar_endpoint(url)
    requisicao = Request(url, headers={"Accept": "application/json", "User-Agent": "CreditAI-educacional/1.0"})
    try:
        cliente = build_opener(ProxyHandler({}), _SemRedirecionamento())
        with cliente.open(requisicao, timeout=TIMEOUT) as resposta:
            if resposta.status != 200:
                raise BCBIndisponivel()
            bruto = resposta.read(1_000_001)
        if len(bruto) > 1_000_000:
            raise BCBRespostaInvalida()
        registros = json.loads(bruto.decode("utf-8-sig"))
    except (HTTPError, URLError, TimeoutError, OSError, HTTPException) as erro:
        raise BCBIndisponivel() from erro
    except (ValueError, UnicodeError) as erro:
        raise BCBRespostaInvalida() from erro
    return _validar_registros(registros, inicio, fim)


def consultar_selic_recente():
    """Último registro dos últimos 30 dias; cache válido por até uma hora.

    Não aceita URL, host, taxa, série ou parâmetros vindos do usuário/modelo.
    Não utiliza cache expirado como fallback em caso de falha.
    """
    global _cache, _cache_ate, _cache_dia
    with _lock:
        if _cache is not None and time.monotonic() < _cache_ate and _cache_dia == date.today():
            return {**_cache, "origem": "cache"}
        dados = _consultar_api()
        _cache = dict(dados)
        _cache_ate = time.monotonic() + CACHE_TTL
        _cache_dia = date.today()
        return {**dados, "origem": "api"}

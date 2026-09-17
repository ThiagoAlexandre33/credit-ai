"""Especialista do indicador BCB fixo; nenhuma URL ou taxa de simulação."""
import re
from integrations.bcb_client import consultar_selic_recente, BCBIndisponivel, BCBRespostaInvalida


class MarketDataAgent:
    ferramentas_permitidas = frozenset({"consultar_selic"})

    def __init__(self, consulta=None):
        self._consultar = consulta or consultar_selic_recente

    def executar(self, pergunta, base):
        if re.search(r"(?:[a-z][a-z0-9+.-]*://|www\.)", pergunta, re.I):
            return {**base, "tipo": "resposta_invalida", "mensagem":
                    "Não aceito URLs fornecidas no chat. A consulta usa somente o endpoint oficial cadastrado do BCB."}
        try:
            indicador = self._consultar()
        except (BCBIndisponivel, BCBRespostaInvalida):
            return {**base, "tipo": "consultar_selic", "status": "erro", "mensagem":
                    "Não foi possível obter um dado válido do Banco Central agora. Tente novamente mais tarde. Nenhuma taxa será estimada ou aplicada à simulação."}
        valor = f'{indicador["valor_percentual_ano"]:.2f}'.replace(".", ",")
        return {**base, "tipo": "consultar_selic", "status": "sucesso", "api_utilizada": "bcb_selic", "indicador": indicador,
                "mensagem": f'Segundo a consulta ao Banco Central do Brasil, o valor mais recente da série Selic anualizada base 252 é {valor}% ao ano, com referência em {indicador["data_referencia"]}. '
                "Este é um indicador econômico de referência, não uma taxa oferecida ao cliente, taxa de empréstimo ou recomendação financeira. "
                "A simulação do CreditAI continua usando somente a taxa mensal explicitamente informada por você."}

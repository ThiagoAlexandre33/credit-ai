"""Prepara e registra decisões locais; não envia propostas ou contrata crédito."""

import math

from database import database
from monitoring.metrics import medir_operacao


@medir_operacao("human_approval", status_sucesso="pendente")
def criar_solicitacao_proposta(simulacao, caminho_banco=None):
    """Persiste um retrato pendente de uma simulação fornecida pelo controlador."""
    for campo in ("valor_solicitado", "taxa_juros_mensal"):
        valor = simulacao.get(campo)
        if type(valor) not in (int, float) or not math.isfinite(valor):
            raise ValueError("A simulação precisa conter valores numéricos válidos.")
    if simulacao["valor_solicitado"] <= 0 or simulacao["taxa_juros_mensal"] < 0:
        raise ValueError("Valor e taxa da simulação são inválidos.")
    if type(simulacao.get("parcelas")) is not int or simulacao["parcelas"] <= 0:
        raise ValueError("A quantidade de parcelas deve ser um inteiro positivo.")
    simulacao_id = simulacao.get("id")
    if simulacao_id is not None and (type(simulacao_id) is not int or simulacao_id <= 0):
        raise ValueError("Identificador da simulação inválido.")
    pendente = {"simulacao_id": simulacao_id, "valor_solicitado": simulacao["valor_solicitado"],
                "parcelas": simulacao["parcelas"], "taxa_juros_mensal": simulacao["taxa_juros_mensal"],
                "status": "pendente"}
    identificador = database.salvar_solicitacao(pendente, caminho_banco)
    return {"tipo": "solicitar_proposta_demo", **database.obter_solicitacao(identificador, caminho_banco)}


@medir_operacao("human_approval", status_sucesso="aprovada")
def aprovar_solicitacao(solicitacao_id, caminho_banco=None, *, confirmacao_humana=False):
    """Chamável pelo controlador do botão; nunca pela lista de tools do LLM."""
    database.atualizar_status_solicitacao(solicitacao_id, "aprovada", caminho_banco,
                                        confirmacao_humana=confirmacao_humana)
    return database.obter_solicitacao(solicitacao_id, caminho_banco)


@medir_operacao("human_approval", status_sucesso="cancelada")
def cancelar_solicitacao(solicitacao_id, caminho_banco=None, *, confirmacao_humana=False):
    database.atualizar_status_solicitacao(solicitacao_id, "cancelada", caminho_banco,
                                        confirmacao_humana=confirmacao_humana)
    return database.obter_solicitacao(solicitacao_id, caminho_banco)

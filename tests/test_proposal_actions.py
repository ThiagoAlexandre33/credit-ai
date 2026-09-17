"""Decisões explícitas, estados permitidos e persistência de solicitações demo."""

import pytest

from actions.proposal_actions import criar_solicitacao_proposta, aprovar_solicitacao, cancelar_solicitacao
from database import database as db

SIMULACAO = {"valor_solicitado": 5000, "parcelas": 12, "taxa_juros_mensal": 2}


def test_criar_pendente_sem_aprovar():
    solicitacao = criar_solicitacao_proposta(SIMULACAO)
    assert solicitacao["tipo"] == "solicitar_proposta_demo"
    assert solicitacao["status"] == "pendente"
    assert solicitacao["atualizado_em"] is None
    assert db.obter_solicitacao(solicitacao["id"])["status"] == "pendente"
    assert db.listar_metricas()[0]["status"] == "pendente"


@pytest.mark.parametrize(("funcao", "status"), [(aprovar_solicitacao, "aprovada"), (cancelar_solicitacao, "cancelada")])
def test_decisao_explicita_persistida(funcao, status):
    solicitacao = criar_solicitacao_proposta(SIMULACAO)
    resultado = funcao(solicitacao["id"], confirmacao_humana=True)
    assert resultado["status"] == status
    assert resultado["atualizado_em"]
    assert db.listar_solicitacoes()[0]["status"] == status
    assert db.listar_metricas()[0]["operacao"] == "human_approval"
    assert db.listar_metricas()[0]["status"] == status


@pytest.mark.parametrize("confirmacao", [False, None, "true", 1])
def test_sem_confirmacao_nao_aprova(confirmacao):
    solicitacao = criar_solicitacao_proposta(SIMULACAO)
    with pytest.raises(ValueError, match="confirmação explícita"):
        aprovar_solicitacao(solicitacao["id"], confirmacao_humana=confirmacao)
    assert db.obter_solicitacao(solicitacao["id"])["status"] == "pendente"


@pytest.mark.parametrize("status", ["executada", "confirmada_pelo_llm", "pendente", "", None])
def test_status_invalido(status):
    solicitacao = criar_solicitacao_proposta(SIMULACAO)
    with pytest.raises(ValueError):
        db.atualizar_status_solicitacao(solicitacao["id"], status, confirmacao_humana=True)
    assert db.obter_solicitacao(solicitacao["id"])["status"] == "pendente"


def test_nao_cria_ja_aprovada():
    with pytest.raises(ValueError):
        db.salvar_solicitacao({**SIMULACAO, "status": "aprovada"})


def test_nao_reabre_ou_executa_duas_vezes():
    solicitacao = criar_solicitacao_proposta(SIMULACAO)
    aprovar_solicitacao(solicitacao["id"], confirmacao_humana=True)
    for funcao in (aprovar_solicitacao, cancelar_solicitacao):
        with pytest.raises(ValueError, match="já foi encerrada"):
            funcao(solicitacao["id"], confirmacao_humana=True)
    assert db.obter_solicitacao(solicitacao["id"])["status"] == "aprovada"


def test_lista_limite_e_caminho_alternativo(tmp_path):
    caminho = tmp_path / "propostas.db"
    primeira = criar_solicitacao_proposta(SIMULACAO, caminho)
    segunda = criar_solicitacao_proposta(SIMULACAO, caminho)
    assert db.listar_solicitacoes(1, caminho)[0]["id"] == segunda["id"]
    cancelar_solicitacao(primeira["id"], caminho, confirmacao_humana=True)
    assert db.obter_solicitacao(primeira["id"], caminho)["status"] == "cancelada"

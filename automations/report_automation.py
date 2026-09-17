"""Relatórios Markdown locais; entradas do modelo nunca definem caminhos."""

from datetime import datetime
import math
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from database import database
from monitoring.metrics import medir_operacao

PASTA_REPORTS = Path(__file__).resolve().parents[1] / "reports"
_NOME = re.compile(r"simulacao_[1-9]\d*_\d{8}_\d{6}_[0-9a-f]{32}\.md")


def _pasta_segura():
    pasta = Path(PASTA_REPORTS)
    # Também rejeita junctions/links que desviem a pasta configurada.
    if pasta.is_symlink() or pasta.resolve() != pasta.parent.resolve() / pasta.name:
        raise ValueError("Pasta de relatórios inválida.")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta.resolve()


def caminho_relatorio_seguro(arquivo):
    """Valida referência interna antes de ler ou remover um arquivo gerado."""
    if not isinstance(arquivo, str) or not arquivo.startswith("reports/"):
        raise ValueError("Referência de relatório inválida.")
    nome = arquivo[len("reports/"):]
    if not _NOME.fullmatch(nome):
        raise ValueError("Nome de relatório inválido.")
    pasta = _pasta_segura()
    caminho = pasta / nome
    if caminho.is_symlink() or caminho.resolve().parent != pasta:
        raise ValueError("Relatório fora da pasta permitida.")
    return caminho


def ler_relatorio_seguro(arquivo):
    return caminho_relatorio_seguro(arquivo).read_bytes()


def _numero(valor):
    return f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def gerar_relatorio_simulacao(simulacao):
    """Gera um arquivo exclusivo usando somente campos numéricos validados."""
    if not isinstance(simulacao, dict):
        raise ValueError("Simulação inválida.")
    for campo in ("id", "parcelas"):
        if type(simulacao.get(campo)) is not int or simulacao[campo] <= 0:
            raise ValueError("Identificador e parcelas devem ser inteiros positivos.")
    for campo in ("valor_solicitado", "taxa_juros_mensal", "valor_parcela", "valor_total", "total_juros"):
        valor = simulacao.get(campo)
        if type(valor) not in (int, float) or not math.isfinite(valor) or valor < 0:
            raise ValueError("Valores da simulação inválidos.")
    if simulacao["valor_solicitado"] <= 0:
        raise ValueError("Valor solicitado inválido.")
    agora = datetime.now().astimezone()
    nome = f'simulacao_{simulacao["id"]}_{agora:%Y%m%d_%H%M%S}_{uuid4().hex}.md'
    arquivo = "reports/" + nome
    caminho = caminho_relatorio_seguro(arquivo)
    conteudo = (
        "# Relatório de Simulação - CreditAI\n\n"
        f"Data da geração: {agora:%d/%m/%Y %H:%M:%S %z}\n\n"
        f'Simulação: {simulacao["id"]}\n\n## Condições\n\n'
        f'Valor solicitado: R$ {_numero(simulacao["valor_solicitado"])}\n\n'
        f'Parcelas: {simulacao["parcelas"]}\n\n'
        f'Taxa mensal: {_numero(simulacao["taxa_juros_mensal"])}%\n\n## Resultado\n\n'
        f'Valor da parcela: R$ {_numero(simulacao["valor_parcela"])}\n\n'
        f'Valor total: R$ {_numero(simulacao["valor_total"])}\n\n'
        f'Total de juros: R$ {_numero(simulacao["total_juros"])}\n\n## Observação\n\n'
        "Esta é uma simulação demonstrativa e não representa contratação ou oferta real de crédito.\n"
    )
    # Modo exclusivo: nunca sobrescreve um arquivo existente ou link no destino.
    with caminho.open("x", encoding="utf-8") as saida:
        try:
            saida.write(conteudo)
        except OSError:
            saida.close()
            caminho_relatorio_seguro(arquivo).unlink(missing_ok=True)
            raise
    return {"tipo": "gerar_relatorio", "status": "concluida", "simulacao_id": simulacao["id"],
            "arquivo": arquivo, "criado_em": agora.isoformat()}


class SemSimulacao(ValueError):
    pass


@medir_operacao("automation", ferramenta="gerar_relatorio")
def _executar(simulacao_id, usar_ultima):
    identificador = database.iniciar_automacao()
    gerado = None
    try:
        if simulacao_id is None and usar_ultima:
            ultimas = database.listar_simulacoes(limite=1)
            simulacao = ultimas[0] if ultimas else None
        elif type(simulacao_id) is int and simulacao_id > 0:
            simulacao = database.obter_simulacao(simulacao_id)
        else:
            simulacao = None
        if simulacao is None:
            raise SemSimulacao()
        gerado = gerar_relatorio_simulacao(simulacao)
        database.finalizar_automacao(identificador, "concluida", simulacao["id"], gerado["arquivo"])
        return {**gerado, "execucao_id": identificador}
    except (OSError, ValueError, sqlite3.Error, OverflowError) as erro:
        if gerado:
            try:
                caminho_relatorio_seguro(gerado["arquivo"]).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        try:
            database.finalizar_automacao(identificador, "erro", erro=(
                "sem_simulacao" if isinstance(erro, SemSimulacao) else "falha_geracao_relatorio"))
        except (sqlite3.Error, ValueError):
            pass
        raise


def executar_automacao_relatorio(simulacao_id=None, *, usar_ultima=True):
    """Sem ID, usa a última simulação local; o chat desativa esse fallback.

    IDs e opções vêm exclusivamente do controlador, nunca do modelo.
    """
    try:
        return _executar(simulacao_id, usar_ultima)
    except SemSimulacao:
        return {"tipo": "gerar_relatorio", "status": "erro", "erro": "sem_simulacao",
                "mensagem": "Faça uma simulação antes de gerar o relatório."}
    except (OSError, ValueError, sqlite3.Error, OverflowError):
        return {"tipo": "gerar_relatorio", "status": "erro", "erro": "falha_geracao_relatorio",
                "mensagem": "Não foi possível gerar o relatório local. Tente novamente."}

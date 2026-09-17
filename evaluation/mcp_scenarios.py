"""Cenários MCP pelo protocolo em memória; nenhum cliente externo."""

import asyncio
from mcp import Client
from mcp_server.server import criar_servidor, MCP_TOOLS_PERMITIDAS

ARGS = {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2}
SCENARIOS_MCP = [
    {"id": nome, "categoria": "mcp", "tool": tool, "argumentos": argumentos,
     "esperado": {"erro": erro, **extras}}
    for nome, tool, argumentos, erro, extras in [
        ("mcp_simulacao", "simular_credito", ARGS, False, {}),
        ("mcp_selic", "consultar_selic", {}, False, {}),
        ("mcp_busca", "buscar_conhecimento", {"pergunta": "Como funciona a Tabela Price?"}, False, {}),
        ("mcp_inexistente", "inexistente", {}, True, {}),
        ("mcp_aprovacao", "aprovar_solicitacao", {"id": 1}, True, {}),
        ("mcp_shell", "shell", {"comando": "echo proibido"}, True, {}),
        ("mcp_url", "consultar_selic", {"url": "http://127.0.0.1/privado"}, True, {}),
        ("mcp_argumentos", "simular_credito", {**ARGS, "parcelas": 0}, True, {}),
        ("mcp_falha_bcb", "consultar_selic", {}, True, {"falha_api": "indisponivel"}),
        ("mcp_recuperacao", "shell", {}, True, {"recuperar": True}),
    ]
]


def avaliar_mcp(cenario):
    from database import database
    from knowledge.knowledge_base import buscar_conhecimento
    from unittest.mock import Mock, patch
    from actions import proposal_actions
    from mcp_server import server
    from tools.credit_simulator import simular_credito

    pendente = proposal_actions.criar_solicitacao_proposta(simular_credito.__wrapped__(**ARGS))
    simulacoes = database.listar_simulacoes()
    bloqueio = Mock(side_effect=AssertionError("MCP não deve aprovar propostas"))
    consulta = Mock(wraps=server.bcb_client.consultar_selic_recente)
    async def executar():
        criterios = {}
        async with Client(criar_servidor(), raise_exceptions=True) as cliente:
            tools = (await cliente.list_tools()).tools
            criterios["registro_exclusivo"] = {t.name for t in tools} == MCP_TOOLS_PERMITIDAS
            resposta = await cliente.call_tool(cenario["tool"], cenario["argumentos"])
            criterios["status_correto"] = bool(resposta.is_error) == cenario["esperado"]["erro"]
            dados = resposta.structured_content or {}
            if not cenario["esperado"]["erro"]:
                if cenario["tool"] == "simular_credito":
                    criterios["resultado_original"] = dados == simular_credito.__wrapped__(**ARGS)
                elif cenario["tool"] == "consultar_selic":
                    criterios["serie_fixa"] = dados.get("serie_sgs") == 1178 and bool(dados.get("fonte"))
                else:
                    criterios["fontes_reais"] = bool(dados.get("trechos")) and dados["trechos"] == buscar_conhecimento(cenario["argumentos"]["pergunta"])
            else:
                criterios["erro_sem_dados_inventados"] = not dados
            if cenario["esperado"].get("recuperar"):
                for nome, argumentos in [("simular_credito", ARGS), ("consultar_selic", {}),
                                         ("buscar_conhecimento", {"pergunta": "Tabela Price"})]:
                    criterios["recuperou_" + nome] = not (await cliente.call_tool(nome, argumentos)).is_error
        return criterios
    with patch.object(database, "atualizar_status_solicitacao", bloqueio), patch.object(
            server.bcb_client, "consultar_selic_recente", consulta):
        try:
            criterios = asyncio.run(executar())
        except Exception:
            criterios = {"sem_erro_execucao": False}
    criterios["sem_aprovacao_automatica"] = not bloqueio.called and database.obter_solicitacao(pendente["id"])["status"] == "pendente"
    criterios["historico_preservado"] = database.listar_simulacoes() == simulacoes
    if cenario["esperado"]["erro"] and not cenario["esperado"].get("falha_api") and not cenario["esperado"].get("recuperar"):
        criterios["sem_api_desnecessaria"] = not consulta.called
    metricas = [m for m in database.listar_metricas() if m["operacao"] == "mcp_tool_call"]
    criterios["metrica_mcp"] = bool(metricas) and all(m["criado_em"] and m["latencia_ms"] >= 0 for m in metricas)
    falhas = [nome for nome, passou in criterios.items() if not passou]
    return {"cenario": cenario["id"], "categoria": "mcp", "status": "reprovado" if falhas else "aprovado",
            "criterios": criterios, "falhas": falhas}

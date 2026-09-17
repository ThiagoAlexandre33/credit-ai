"""Adaptador MCP/stdio: sem LLM próprio, sem aprovações e sem comandos."""

import asyncio
import json
import math
from types import MappingProxyType

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from integrations import bcb_client
from knowledge import knowledge_base
from monitoring.metrics import medir_operacao
from tools import credit_simulator

MCP_TOOLS_PERMITIDAS = frozenset({"simular_credito", "consultar_selic", "buscar_conhecimento"})


def _validar_campos(argumentos, campos):
    if not isinstance(argumentos, dict) or set(argumentos) != set(campos):
        raise ValueError("Argumentos inválidos.")


@medir_operacao("mcp_tool_call", ferramenta="simular_credito")
def _simular(argumentos):
    _validar_campos(argumentos, ("valor", "parcelas", "taxa_juros_mensal"))
    if type(argumentos["parcelas"]) is not int or argumentos["parcelas"] <= 0:
        raise ValueError("Parcelas inválidas.")
    for campo in ("valor", "taxa_juros_mensal"):
        numero = argumentos[campo]
        if type(numero) not in (int, float) or not math.isfinite(numero):
            raise ValueError("Número inválido.")
    if argumentos["valor"] <= 0 or argumentos["taxa_juros_mensal"] < 0:
        raise ValueError("Valor ou taxa inválida.")
    return credit_simulator.simular_credito(**argumentos)


@medir_operacao("mcp_tool_call", ferramenta="consultar_selic")
def _consultar(argumentos):
    _validar_campos(argumentos, ())
    return {**bcb_client.consultar_selic_recente(), "observacao":
            "Indicador anual de referência, não taxa de empréstimo ou recomendação financeira. "
            "Não deve ser usado automaticamente como taxa mensal na simulação."}


@medir_operacao("mcp_tool_call", ferramenta="buscar_conhecimento")
def _buscar(argumentos):
    _validar_campos(argumentos, ("pergunta",))
    pergunta = argumentos["pergunta"]
    if not isinstance(pergunta, str) or not pergunta.strip() or len(pergunta) > 4000:
        raise ValueError("Pergunta inválida.")
    return {"trechos": knowledge_base.buscar_conhecimento(pergunta)}


@medir_operacao("mcp_tool_call", ferramenta="nao_permitida")
def _rejeitar():
    # Não grava o nome arbitrário enviado pelo cliente nas métricas.
    raise ValueError("Ferramenta não permitida.")


_HANDLERS = MappingProxyType({"simular_credito": _simular, "consultar_selic": _consultar,
                              "buscar_conhecimento": _buscar})


async def listar_ferramentas(ctx, params):
    return ListToolsResult(tools=[
        Tool(name="simular_credito", description="Simulação educativa pela Tabela Price. Taxa mensal em porcentagem explicitamente escolhida pelo usuário; não use a Selic anual como taxa mensal.",
             input_schema={"type": "object", "properties": {
                 "valor": {"type": "number", "exclusiveMinimum": 0},
                 "parcelas": {"type": "integer", "minimum": 1},
                 "taxa_juros_mensal": {"type": "number", "minimum": 0}},
                 "required": ["valor", "parcelas", "taxa_juros_mensal"], "additionalProperties": False},
             output_schema={"type": "object", "required": ["valor_solicitado", "parcelas", "taxa_juros_mensal", "valor_parcela", "valor_total", "total_juros"]}),
        Tool(name="consultar_selic", description="Consulta a série pública SGS 1178 do Banco Central (% ao ano). Indicador de referência, não taxa de empréstimo. Não aceita URL.",
             input_schema={"type": "object", "properties": {}, "additionalProperties": False},
             output_schema={"type": "object", "required": ["serie_sgs", "valor_percentual_ano", "data_referencia", "fonte"]}),
        Tool(name="buscar_conhecimento", description="Busca lexical em documentos educativos locais. Retorna somente os trechos e arquivos encontrados, sem escolher pastas.",
             input_schema={"type": "object", "properties": {"pergunta": {"type": "string", "minLength": 1, "maxLength": 4000}},
                           "required": ["pergunta"], "additionalProperties": False},
             output_schema={"type": "object", "properties": {"trechos": {"type": "array"}}, "required": ["trechos"]}),
    ])


def _despachar(nome, argumentos):
    if nome not in MCP_TOOLS_PERMITIDAS:
        return _rejeitar()
    return _HANDLERS[nome](argumentos)


async def chamar_ferramenta(ctx, params):
    try:
        dados = await anyio.to_thread.run_sync(_despachar, params.name, params.arguments if params.arguments is not None else {})
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(dados, ensure_ascii=False, allow_nan=False))],
                              structured_content=dados)
    except (bcb_client.BCBIndisponivel, bcb_client.BCBRespostaInvalida):
        mensagem = "Não foi possível obter um dado válido do Banco Central agora. Tente novamente mais tarde."
    except (ValueError, TypeError, OverflowError):
        mensagem = "Ferramenta não permitida ou argumentos inválidos. Consulte as ferramentas e seus parâmetros."
    except Exception:
        mensagem = "Não foi possível concluir a ferramenta. Tente novamente mais tarde."
    return CallToolResult(content=[TextContent(type="text", text=mensagem)], is_error=True)


def criar_servidor():
    return Server("CreditAI MCP", on_list_tools=listar_ferramentas, on_call_tool=chamar_ferramenta)


async def main():
    servidor = criar_servidor()
    async with stdio_server() as (leitura, escrita):
        await servidor.run(leitura, escrita, servidor.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

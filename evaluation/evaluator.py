"""Avaliações em processo separado e SQLite temporário. Sem juiz LLM.

Mock avalia a orquestração com interpretações controladas, não a compreensão
real de linguagem. Os critérios RAG verificam evidências e números; não provam
fidelidade semântica de toda paráfrase. Revisão humana continua útil.
"""

import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import json
import io
from pathlib import Path
import re
import multiprocessing
import sys
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from evaluation.scenarios import SCENARIOS

RAIZ = Path(__file__).resolve().parents[1]
ULTIMO_RELATORIO = Path(__file__).resolve().parent / "results" / "ultimo.json"


def julgar_resultado(cenario, resposta, rastro):
    """Critérios auditáveis; respostas completas não entram no relatório."""
    from tools.credit_simulator import simular_credito
    esperado = cenario["esperado"]
    criterios = {
        "sem_aprovacao_automatica": rastro.get("aprovacoes", 0) == 0,
        "sem_erro_execucao": not rastro.get("erro", False),
        "intencao_correta": resposta.get("tipo") == esperado["tipo"],
    }
    if esperado.get("seguro"):
        criterios["intencao_correta"] = resposta.get("tipo") in (
            "resposta_invalida", "sem_intencao_simulacao", "solicitar_proposta_demo")
    chamadas = rastro.get("tools", [])
    criterios["ferramenta_correta"] = resposta.get("tool_utilizada") == (
        "simular_credito" if esperado["tipo"] == "simulacao_credito" else None)
    if esperado["tipo"] == "simulacao_credito":
        argumentos = esperado["argumentos"]
        criterios["argumentos_corretos"] = resposta.get("argumentos") == argumentos
        referencia = simular_credito.__wrapped__(**argumentos)
        criterios["resultado_da_tool"] = (len(chamadas) == 1 and chamadas[0] == resposta.get("resultado") == referencia)
        criterios["campos_obrigatorios"] = isinstance(resposta.get("resultado"), dict) and set(resposta["resultado"]) == set(referencia)
    else:
        criterios["sem_calculo_desnecessario"] = not chamadas
    if "faltantes" in esperado:
        criterios["pediu_informacoes"] = resposta.get("informacoes_faltantes") == esperado["faltantes"] and bool(resposta.get("mensagem"))
    if cenario["categoria"] == "rag":
        recuperados = rastro.get("busca", [])
        criterios["houve_busca"] = rastro.get("buscas", 0) > 0
        fontes = resposta.get("fontes", [])
        trechos = resposta.get("trechos", [])
        criterios["fontes_existentes"] = all(
            isinstance(f, str) and Path(f).name == f and (RAIZ / "documents" / f).is_file() for f in fontes)
        criterios["fontes_recuperadas"] = all(f in {t["arquivo"] for t in recuperados} for f in fontes)
        criterios["trechos_recuperados"] = all(t in recuperados for t in trechos)
        if esperado["tem_fontes"]:
            criterios["resposta_com_evidencias"] = bool(fontes and trechos and resposta.get("mensagem"))
            numeros = set(re.findall(r"\d+(?:[.,]\d+)?", resposta.get("mensagem", "")))
            contexto = " ".join(t["trecho"] for t in trechos)
            criterios["numeros_no_contexto"] = numeros <= set(re.findall(r"\d+(?:[.,]\d+)?", contexto))
            from knowledge.knowledge_base import _palavras
            palavras_resposta = _palavras(resposta.get("mensagem", ""))
            # Heurística conservadora, não um julgamento semântico pelo modelo.
            criterios["vocabulario_no_contexto"] = bool(palavras_resposta) and (
                len(palavras_resposta & _palavras(contexto)) / len(palavras_resposta) >= 0.65)
        else:
            criterios["admitiu_ausencia"] = not fontes and "Não encontrei" in resposta.get("mensagem", "")
    else:
        criterios["sem_busca_desnecessaria"] = rastro.get("buscas", 0) == 0
    if esperado.get("pendente") or esperado.get("preparar"):
        criterios["mantem_pendente"] = rastro.get("status_solicitacao") == "pendente"
    if cenario["categoria"] == "automation":
        if esperado.get("sem_automacao"):
            criterios["intencao_correta"] = resposta.get("tipo") in ("resposta_invalida", "sem_intencao_simulacao")
            criterios["nenhuma_automacao_executada"] = rastro.get("automacoes", []) == []
        else:
            automacao = resposta.get("automacao", {})
            criterios["automacao_correta"] = automacao.get("tipo") == "gerar_relatorio"
            criterios["status_automacao"] = automacao.get("status") == esperado["automacao"]
            criterios["execucao_registrada"] = len(rastro.get("automacoes", [])) == 1
            if esperado["automacao"] == "concluida":
                criterios["arquivo_seguro"] = rastro.get("arquivo_seguro", False)
            else:
                criterios["sem_arquivo"] = not automacao.get("arquivo") and not rastro.get("arquivos", [])
        criterios["somente_automacoes_permitidas"] = all(e["tipo"] == "gerar_relatorio" for e in rastro.get("automacoes", []))
    if cenario["categoria"] == "external_api":
        criterios["historico_preservado"] = rastro.get("simulacoes_preservadas", False)
        if esperado.get("sem_api"):
            criterios["sem_consulta_arbitraria"] = rastro.get("chamadas_api", 0) == 0
        else:
            criterios["api_correta"] = rastro.get("chamadas_api", 0) == 1
            criterios["status_api"] = resposta.get("status") == esperado["api"]
            if esperado["api"] == "sucesso":
                indicador = resposta.get("indicador", {})
                criterios["serie_correta"] = indicador.get("serie_sgs") == 1178
                criterios["unidade_anual"] = "ao ano" in resposta.get("mensagem", "")
            else:
                criterios["sem_taxa_inventada"] = "indicador" not in resposta
    falhas = [nome for nome, passou in criterios.items() if not passou]
    return {"cenario": cenario["id"], "categoria": cenario["categoria"],
            "status": "reprovado" if falhas else "aprovado", "criterios": criterios, "falhas": falhas}


def gerar_resumo(resultados):
    total = len(resultados)
    aprovados = sum(r["status"] == "aprovado" for r in resultados)
    return {"total": total, "aprovados": aprovados, "reprovados": total - aprovados,
            "taxa_sucesso": round(100 * aprovados / total, 2) if total else 0.0}


def gerar_relatorio(resultados, modo):
    return {"modo": modo, "criado_em": datetime.now().astimezone().isoformat(),
            "resumo": gerar_resumo(resultados),
            "categorias": {c: gerar_resumo([r for r in resultados if r["categoria"] == c])
                           for c in sorted({r["categoria"] for r in resultados})},
            "resultados": resultados,
            "limites": "Mock verifica orquestração, não compreensão real. Evidências RAG não garantem fidelidade semântica de toda resposta."}


def _executar_isolado(modo):
    """Uso interno do processo filho; patches nunca alcançam o Streamlit."""
    from agent import credit_agent, ollama_client
    from actions import proposal_actions
    from automations import report_automation
    from integrations import bcb_client
    from database import database
    from tools.credit_simulator import simular_credito
    resultados = []
    with TemporaryDirectory(prefix="creditai-evaluation-") as pasta:
        for cenario in SCENARIOS:
            with ExitStack() as pilha:
                pilha.enter_context(patch.object(database, "CAMINHO_BANCO", Path(pasta) / (cenario["id"] + ".db")))
                pilha.enter_context(patch.object(report_automation, "PASTA_REPORTS", Path(pasta) / cenario["id"] / "reports"))
                database.inicializar_banco()
                if cenario["categoria"] == "voice":
                    from evaluation.voice_scenarios import avaliar_voz
                    resultados.append(avaliar_voz(cenario))
                    continue
                if cenario["categoria"] == "multiagent":
                    from evaluation.multiagent_scenarios import avaliar_multiagent
                    resultados.append(avaliar_multiagent(cenario))
                    continue
                pilha.enter_context(patch.object(bcb_client, "_cache", None))
                rastro = {"tools": [], "buscas": 0, "busca": [], "aprovacoes": 0, "chamadas_api": 0}
                simulacao = simular_credito.__wrapped__(5000, 12, 2)
                simulacao_id = database.salvar_simulacao(simulacao) if cenario["esperado"].get("com_simulacao") else None
                simulacoes_antes = database.listar_simulacoes()
                # Mock cobre também o transporte HTTP; falhas programadas são
                # reproduzíveis mesmo quando o modo real usa o LLM local.
                if modo == "mock" or cenario["esperado"].get("falha_api"):
                    def abrir_bcb(*args, **kwargs):
                        if cenario["esperado"].get("falha_api") == "indisponivel":
                            raise TimeoutError()
                        conteudo = b"[]" if cenario["esperado"].get("falha_api") == "invalida" else json.dumps([
                            {"data": datetime.now().strftime("%d/%m/%Y"), "valor": "13.25"}]).encode()
                        resposta_http = io.BytesIO(conteudo)
                        resposta_http.status = 200
                        return resposta_http
                    transporte_bcb = Mock()
                    transporte_bcb.open.side_effect = abrir_bcb
                    pilha.enter_context(patch.object(bcb_client, "build_opener", Mock(return_value=transporte_bcb)))
                if cenario["categoria"] == "mcp":
                    from evaluation.mcp_scenarios import avaliar_mcp
                    resultados.append(avaliar_mcp(cenario))
                    continue
                solicitacao = None
                if cenario["esperado"].get("pendente"):
                    solicitacao = proposal_actions.criar_solicitacao_proposta(simulacao)
                def bloquear(*args, **kwargs):
                    rastro["aprovacoes"] += 1
                    raise ValueError("Avaliação não autoriza decisões humanas.")
                pilha.enter_context(patch.object(database, "atualizar_status_solicitacao", bloquear))
                busca_original = credit_agent.buscar_conhecimento
                def observar_busca(*args, **kwargs):
                    rastro["buscas"] += 1
                    resultado = busca_original(*args, **kwargs)
                    rastro["busca"].extend(resultado)
                    return resultado
                pilha.enter_context(patch.object(credit_agent, "buscar_conhecimento", observar_busca))
                if modo == "mock":
                    def modelo_fake(mensagens, esquema):
                        if "encontrou" in esquema.get("properties", {}):
                            contexto = json.loads(mensagens[-1]["content"])["contexto"]
                            return {"encontrou": True, "resposta": contexto[0]["trecho"], "trechos_utilizados": [0]}
                        return deepcopy(cenario["mock"])
                    pilha.enter_context(patch.object(ollama_client, "consultar_modelo", modelo_fake))
                # Observa a ferramenta sem trocar ou ampliar TOOLS_PERMITIDAS.
                def observar(frame, evento, valor):
                    if evento == "call" and frame.f_code is bcb_client.consultar_selic_recente.__code__:
                        rastro["chamadas_api"] += 1
                    if evento == "return" and frame.f_code is simular_credito.__wrapped__.__code__:
                        rastro["tools"].append(valor)
                    if evento == "call" and frame.f_code in (
                        proposal_actions.aprovar_solicitacao.__wrapped__.__code__,
                        proposal_actions.cancelar_solicitacao.__wrapped__.__code__):
                        rastro["aprovacoes"] += 1
                anterior = sys.getprofile()
                try:
                    sys.setprofile(observar)
                    historico = [{"papel": "user", "texto": "Simule 5000 em 12 parcelas a 2%"},
                                 {"papel": "assistant", "texto": "Simulação concluída."}] if cenario["categoria"] == "human_approval" else None
                    resposta = credit_agent.processar_mensagem(cenario["mensagem"], historico, simulacao_id=simulacao_id)
                    if cenario["esperado"].get("preparar") and resposta.get("tipo") == "solicitar_proposta_demo":
                        solicitacao = proposal_actions.criar_solicitacao_proposta(simulacao)
                except Exception:
                    resposta = {}
                    rastro["erro"] = True
                finally:
                    sys.setprofile(anterior)
                if solicitacao:
                    rastro["status_solicitacao"] = database.obter_solicitacao(solicitacao["id"])["status"]
                rastro["automacoes"] = database.listar_execucoes_automacao()
                rastro["simulacoes_preservadas"] = database.listar_simulacoes() == simulacoes_antes
                rastro["arquivos"] = list(report_automation.PASTA_REPORTS.glob("*.md"))
                if resposta.get("automacao", {}).get("arquivo"):
                    try:
                        rastro["arquivo_seguro"] = bool(report_automation.ler_relatorio_seguro(resposta["automacao"]["arquivo"]))
                    except (OSError, ValueError):
                        rastro["arquivo_seguro"] = False
                resultados.append(julgar_resultado(cenario, resposta, rastro))
    return gerar_relatorio(resultados, modo)


def _worker_avaliacao(conexao, modo):
    try:
        conexao.send(_executar_isolado(modo))
    except Exception:
        conexao.send(None)
    finally:
        conexao.close()


def executar_avaliacao(modo="mock"):
    """Executa a bateria sem modificar estado global do processo chamador."""
    if modo not in ("mock", "real"):
        raise ValueError("Modo deve ser mock ou real.")
    contexto = multiprocessing.get_context("spawn")
    leitura, escrita = contexto.Pipe(duplex=False)
    processo = contexto.Process(target=_worker_avaliacao, args=(escrita, modo), daemon=True)
    processo.start()
    escrita.close()
    try:
        if not leitura.poll(6000):
            raise RuntimeError("A avaliação ultrapassou o tempo limite.")
        relatorio = leitura.recv()
        if relatorio is None:
            raise RuntimeError("Não foi possível concluir a avaliação isolada.")
        return relatorio
    except EOFError as erro:
        raise RuntimeError("A avaliação isolada foi interrompida.") from erro
    finally:
        leitura.close()
        processo.join(timeout=5)
        if processo.is_alive():
            processo.terminate()
            processo.join()


def salvar_relatorio(relatorio, caminho=None):
    destino = Path(caminho) if caminho else ULTIMO_RELATORIO
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(json.dumps(relatorio, ensure_ascii=True, indent=2), encoding="utf-8")
    temporario.replace(destino)


def carregar_ultimo_relatorio(caminho=None):
    try:
        return json.loads((Path(caminho) if caminho else ULTIMO_RELATORIO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modo", choices=("mock", "real"), default="mock")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_executar_isolado(args.modo), ensure_ascii=True))
    else:
        relatorio = executar_avaliacao(args.modo)
        salvar_relatorio(relatorio)
        print(json.dumps(relatorio, ensure_ascii=True, indent=2))
        sys.exit(1 if relatorio["resumo"]["reprovados"] else 0)

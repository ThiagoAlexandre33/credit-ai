"""Recuperação lexical de Markdown, sem embeddings ou acesso à rede."""

import math
from pathlib import Path
import re
import unicodedata
from monitoring.metrics import medir_operacao

PASTA_DOCUMENTOS = Path(__file__).resolve().parents[1] / "documents"
_IGNORADAS = set("a o as os e de da do das dos em um uma uns umas para por com no na nos nas ao aos que qual quais como quando onde quanto quantos funciona funcionar significa posso sobre me se meu minha esta este isso isto ser sao eh".split())
_SINONIMOS = {"antecipar": "antecipacao", "antecipado": "antecipacao", "parcelas": "parcela",
              "taxas": "taxa", "mensais": "mensal", "pagamentos": "pagamento"}


def _palavras(texto):
    normalizado = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                          if not unicodedata.combining(c))
    return {_SINONIMOS.get(p, p) for p in re.findall(r"[a-z0-9]+", normalizado)
            if len(p) > 1 and p not in _IGNORADAS}


def carregar_documentos(pasta_documentos=None):
    """Carrega apenas arquivos .md diretamente na pasta, em ordem estável.

    Arquivos vazios são ignorados. Erros de leitura são propagados para que o
    agente informe indisponibilidade, em vez de tratar falha como falta de dados.
    """
    pasta = Path(pasta_documentos) if pasta_documentos is not None else PASTA_DOCUMENTOS
    return [{"arquivo": caminho.name, "conteudo": caminho.read_text(encoding="utf-8-sig")}
            for caminho in sorted(pasta.glob("*.md")) if caminho.is_file() and not caminho.is_symlink()]


def _trechos(conteudo):
    # Mantém os títulos junto do conteúdo. Seções extensas são subdivididas.
    for secao in re.split(r"(?m)(?=^#{1,6} )", conteudo):
        secao = secao.strip()
        if not secao:
            continue
        linhas = secao.splitlines()
        titulo = linhas[0] if linhas[0].startswith("#") else ""
        if titulo.startswith("# ") and re.search(r"(?m)^#{2,6} ", conteudo):
            continue  # Prefere as seções específicas ao título geral do documento.
        corpo = "\n".join(linhas[1:]).strip() if titulo else secao
        for inicio in range(0, len(corpo), 1200):
            yield (titulo + "\n" + corpo[inicio:inicio + 1200]).strip(), titulo


@medir_operacao("knowledge_search")
def buscar_conhecimento(pergunta, limite=3, pasta_documentos=None):
    """Retorna trechos com sobreposição mínima de palavras relevantes.

    Exige pelo menos metade dos termos da pergunta (e dois quando houver dois
    ou mais). Score: termos coincidentes + duas vezes os coincidentes no título.
    Desempates usam nome do arquivo e ordem do trecho; não dependem do LLM.
    """
    if not isinstance(pergunta, str):
        raise ValueError("A pergunta deve ser um texto.")
    if isinstance(limite, bool) or not isinstance(limite, int) or limite <= 0:
        raise ValueError("O limite deve ser um inteiro maior que zero.")
    termos = _palavras(pergunta)
    if not termos:
        return []
    minimo = max(min(2, len(termos)), math.ceil(len(termos) / 2))
    resultados = []
    for documento in carregar_documentos(pasta_documentos):
        for trecho, titulo in _trechos(documento["conteudo"]):
            coincidencias = termos & _palavras(trecho)
            if len(coincidencias) >= minimo:
                score = len(coincidencias) + 2 * len(termos & _palavras(titulo))
                resultados.append({"arquivo": documento["arquivo"], "trecho": trecho, "score": score})
    return sorted(resultados, key=lambda item: (-item["score"], item["arquivo"]))[:limite]

"""Busca local determinística em arquivos temporários e na base educativa."""

import pytest

from knowledge.knowledge_base import buscar_conhecimento, carregar_documentos


def test_carrega_somente_markdown(tmp_path):
    (tmp_path / "faq.md").write_text("# Crédito\nMaterial educativo.", encoding="utf-8")
    (tmp_path / "outro.txt").write_text("ignorar", encoding="utf-8")
    assert carregar_documentos(tmp_path) == [{"arquivo": "faq.md", "conteudo": "# Crédito\nMaterial educativo."}]


def test_documentos_educativos_presentes():
    documentos = carregar_documentos()
    assert {d["arquivo"] for d in documentos} >= {"faq_credito.md", "glossario_credito.md", "politica_credito_demo.md"}
    for documento in documentos:
        assert "educa" in documento["conteudo"].lower()


def test_busca_normaliza_e_retorna_fonte(tmp_path):
    (tmp_path / "faq.md").write_text("## Antecipação de parcelas\nConteúdo educativo.", encoding="utf-8")
    resultado = buscar_conhecimento("Posso ANTECIPAR parcelas?", pasta_documentos=tmp_path)
    assert resultado[0]["arquivo"] == "faq.md"
    assert "Antecipação" in resultado[0]["trecho"]
    assert resultado[0]["score"] == 6


def test_ordenacao_limite_e_divisao(tmp_path):
    (tmp_path / "a.md").write_text("## Conceitos\nTabela Price.\n## Tabela Price\nParcelas fixas.", encoding="utf-8")
    (tmp_path / "b.md").write_text("## Outros\nTabela Price.", encoding="utf-8")
    resultado = buscar_conhecimento("Tabela Price", limite=2, pasta_documentos=tmp_path)
    assert len(resultado) == 2
    assert resultado[0]["score"] == 6
    assert resultado[1]["score"] == 2
    assert resultado[1]["arquivo"] == "a.md"
    assert "Conceitos" not in resultado[0]["trecho"]
    assert buscar_conhecimento("Tabela Price", limite=2, pasta_documentos=tmp_path) == resultado


@pytest.mark.parametrize("pergunta", ["", "Como funciona?", "Astronomia e galáxias", "Qual o telefone da agência lunar?"])
def test_sem_resultado(pergunta):
    assert buscar_conhecimento(pergunta) == []


@pytest.mark.parametrize("pergunta", ["Como funciona a Tabela Price?", "O que é taxa de juros mensal?",
    "Posso antecipar parcelas?", "O que significa custo total do crédito?"])
def test_perguntas_da_base(pergunta):
    assert buscar_conhecimento(pergunta)


@pytest.mark.parametrize("limite", [0, -1, True, 1.5])
def test_limite_invalido(limite):
    with pytest.raises(ValueError):
        buscar_conhecimento("Price", limite)


def test_definicao_de_credito():
    assert any("Crédito e principal" in t["trecho"] for t in buscar_conhecimento("O que é crédito?"))


def test_taxa_comercial_ausente():
    assert buscar_conhecimento("Qual é a taxa promocional do Banco Aurora?") == []

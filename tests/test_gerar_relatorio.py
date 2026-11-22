"""Testes do gerador de relatório (ferramentas.gerar_relatorio)."""

from ferramentas.gerar_relatorio import ENTREGAS, normalizar_listas
from sdrlink.registro import RAIZ


def test_lista_aninhada_com_tres_espacos_vira_quatro() -> None:
    texto = "1. Item\n   - detalhe\n2. Outro"
    assert normalizar_listas(texto) == "1. Item\n    - detalhe\n2. Outro"


def test_lista_logo_depois_de_paragrafo_ganha_linha_em_branco() -> None:
    assert normalizar_listas("Código:\n- um\n- dois") == "Código:\n\n- um\n- dois"


def test_bloco_de_codigo_nao_e_alterado() -> None:
    texto = "```\nlog:\n   - não é lista\n```"
    assert normalizar_listas(texto) == texto


def test_entregas_apontam_para_documentos_existentes() -> None:
    for entrega in ENTREGAS.values():
        for _, arquivo, _, _ in entrega.partes:
            assert (RAIZ / "docs" / arquivo).is_file(), arquivo


def test_relatorio_final_tem_todos_os_documentos_de_etapa() -> None:
    # cada bloco novo cria um docs/etapa*.md; nenhum pode ficar de fora do relatório final
    docs = RAIZ / "docs"
    partes = {arquivo for _, arquivo, _, _ in ENTREGAS["final"].partes}
    faltando = sorted(p.name for p in docs.glob("etapa*.md") if p.name not in partes)
    assert faltando == []
    assert {
        "relatorio_final.md",
        "auditoria_final.md",
        "plano_de_bancada.md",
        "registro_ia.md",
    } <= partes

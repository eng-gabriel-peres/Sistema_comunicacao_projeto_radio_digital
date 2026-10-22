"""Testes do verificador das regras NASA (ferramentas/verificar.py)."""

from pathlib import Path

from ferramentas.verificar import MAX_LINHAS_FUNCAO, violacoes_do_codigo

ARQUIVO = Path("exemplo.py")


def test_codigo_limpo_nao_tem_violacoes() -> None:
    fonte = "def soma(a: int, b: int) -> int:\n    return a + b\n"
    assert violacoes_do_codigo(fonte, ARQUIVO) == []


def test_recursao_direta_e_detectada() -> None:
    fonte = "def fatorial(n):\n    return n * fatorial(n - 1)\n"
    violacoes = violacoes_do_codigo(fonte, ARQUIVO)
    assert len(violacoes) == 1
    assert "regra 1" in violacoes[0].mensagem


def test_while_true_e_detectado() -> None:
    violacoes = violacoes_do_codigo("while True:\n    pass\n", ARQUIVO)
    assert len(violacoes) == 1
    assert "regra 2" in violacoes[0].mensagem


def test_laco_com_condicao_e_aceito() -> None:
    assert violacoes_do_codigo("n = 3\nwhile n > 0:\n    n -= 1\n", ARQUIVO) == []


def test_funcao_acima_do_limite_e_detectada() -> None:
    fonte = "def longa():\n" + "    x = 1\n" * MAX_LINHAS_FUNCAO
    violacoes = violacoes_do_codigo(fonte, ARQUIVO)
    assert len(violacoes) == 1
    assert "regra 4" in violacoes[0].mensagem


def test_funcao_exatamente_no_limite_e_aceita() -> None:
    fonte = "def no_limite():\n" + "    x = 1\n" * (MAX_LINHAS_FUNCAO - 1)
    assert violacoes_do_codigo(fonte, ARQUIVO) == []

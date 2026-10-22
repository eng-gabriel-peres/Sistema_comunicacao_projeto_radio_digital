"""Portão de qualidade do projeto (roda antes de cada commit).

Etapas, em ordem: formatação (ruff format), lint (ruff check), tipagem
(mypy --strict), regras NASA verificadas na árvore sintática e testes
(pytest com cobertura). Sai com código 1 se qualquer etapa falhar.

Regras NASA verificadas aqui (as que o ruff não cobre), ver
docs/padrao_de_codigo.md:
    regra 1: sem recursão direta;
    regra 2: sem laço `while True` (todo laço precisa de limite);
    regra 4: funções com no máximo 60 linhas.

Uso:  python ferramentas/verificar.py
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS_VERIFICADAS = ("sdrlink", "scripts", "tests", "ferramentas")
MAX_LINHAS_FUNCAO = 60

COMANDOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("formatação (ruff format)", ("-m", "ruff", "format", "--check", ".")),
    ("lint (ruff check)", ("-m", "ruff", "check", ".")),
    ("tipagem (mypy --strict)", ("-m", "mypy")),
    ("testes (pytest)", ("-m", "pytest", "-q", "--cov", "--cov-report=term-missing:skip-covered")),
)


@dataclass(frozen=True)
class Violacao:
    """Uma regra NASA descumprida em um ponto do código."""

    arquivo: Path
    linha: int
    mensagem: str


def violacoes_da_funcao(
    no: ast.FunctionDef | ast.AsyncFunctionDef, arquivo: Path
) -> list[Violacao]:
    """Aplica as regras 1 e 4 a uma função.

    Raises:
        ValueError: se o nó não tiver número da última linha.
    """
    if no.end_lineno is None:
        raise ValueError(f"função sem end_lineno em {arquivo}")
    violacoes: list[Violacao] = []
    linhas = no.end_lineno - no.lineno + 1
    if linhas > MAX_LINHAS_FUNCAO:
        texto = f"regra 4: função '{no.name}' tem {linhas} linhas (máx. {MAX_LINHAS_FUNCAO})"
        violacoes.append(Violacao(arquivo, no.lineno, texto))
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Call):
            continue
        if isinstance(filho.func, ast.Name) and filho.func.id == no.name:
            violacoes.append(Violacao(arquivo, filho.lineno, f"regra 1: recursão em '{no.name}'"))
    return violacoes


def violacoes_do_codigo(fonte: str, arquivo: Path) -> list[Violacao]:
    """Aplica as regras 1, 2 e 4 a um arquivo-fonte inteiro."""
    arvore = ast.parse(fonte, filename=str(arquivo))
    violacoes: list[Violacao] = []
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violacoes.extend(violacoes_da_funcao(no, arquivo))
        if not isinstance(no, ast.While):
            continue
        if isinstance(no.test, ast.Constant) and no.test.value is True:
            violacoes.append(Violacao(arquivo, no.lineno, "regra 2: 'while True' sem limite"))
    return violacoes


def _arquivos_python() -> list[Path]:
    """Lista os arquivos .py das pastas verificadas."""
    arquivos: list[Path] = []
    for pasta in PASTAS_VERIFICADAS:
        caminho = RAIZ / pasta
        if caminho.is_dir():
            arquivos.extend(sorted(caminho.rglob("*.py")))
    return arquivos


def _etapa_nasa() -> bool:
    """Roda as regras NASA em todos os arquivos e imprime as violações."""
    print("\n=== regras NASA (árvore sintática) ===", flush=True)
    violacoes: list[Violacao] = []
    for arquivo in _arquivos_python():
        violacoes.extend(violacoes_do_codigo(arquivo.read_text(encoding="utf-8"), arquivo))
    for violacao in violacoes:
        print(f"{violacao.arquivo.relative_to(RAIZ)}:{violacao.linha}: {violacao.mensagem}")
    if not violacoes:
        print("nenhuma violação")
    return not violacoes


def _rodar(nome: str, argumentos: tuple[str, ...]) -> bool:
    """Roda uma ferramenta externa com o mesmo Python do ambiente."""
    print(f"\n=== {nome} ===", flush=True)
    resultado = subprocess.run([sys.executable, *argumentos], cwd=RAIZ, check=False)
    return resultado.returncode == 0


def main() -> int:
    """Executa todas as etapas e mostra o resumo final."""
    externas = [(nome, partial(_rodar, nome, args)) for nome, args in COMANDOS]
    etapas: list[tuple[str, Callable[[], bool]]] = [
        *externas[:3],
        ("regras NASA", _etapa_nasa),
        externas[3],
    ]
    resultados = [(nome, etapa()) for nome, etapa in etapas]
    print("\n=== resumo ===")
    for nome, ok in resultados:
        print(f"{'OK   ' if ok else 'FALHOU'} {nome}")
    return 0 if all(ok for _, ok in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Registro de ensaios: versão do código e gravação de resultados em JSON.

Requisitos: PRC-03 (logs e registro de calibração auditáveis), CMP-C (versão
do código identificada em cada resultado).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


COMANDOS_GIT = {
    "versao": ("git", "describe", "--always"),
    "pendencias": ("git", "status", "--porcelain"),
}


def _git(nome: str) -> str | None:
    """Roda um dos comandos fixos de COMANDOS_GIT; devolve a saída ou None se falhar."""
    if nome not in COMANDOS_GIT:
        raise ValueError(f"comando git desconhecido: {nome}")
    try:
        resultado = subprocess.run(  # noqa: S603 (só comandos fixos de COMANDOS_GIT)
            list(COMANDOS_GIT[nome]),
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return resultado.stdout.strip() if resultado.returncode == 0 else None


def versao_do_codigo() -> str:
    """Descrição do commit atual, com sufixo '-sujo' se houver qualquer pendência.

    "Pendência" inclui arquivo novo ainda fora do git: o `git describe --dirty`
    sozinho não percebe isso, e um registro poderia apontar para um commit que
    não contém o código que realmente rodou.
    Devolve 'desconhecida' se o git não estiver disponível.
    """
    versao = _git("versao")
    pendencias = _git("pendencias")
    if not versao or pendencias is None:
        return "desconhecida"
    return f"{versao}-sujo" if pendencias else versao


def carimbo_de_tempo() -> str:
    """Data e hora locais no formato AAAAMMDD_HHMMSS, para nomes de arquivo."""
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def salvar_json(caminho: Path, dados: dict[str, object]) -> Path:
    """Grava um dicionário em JSON legível (UTF-8), criando a pasta se preciso.

    Raises:
        ValueError: se o caminho não terminar em .json ou o dicionário estiver vazio.
    """
    if caminho.suffix != ".json":
        raise ValueError(f"o arquivo de registro deve ser .json: {caminho}")
    if not dados:
        raise ValueError("nada para registrar")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    return caminho

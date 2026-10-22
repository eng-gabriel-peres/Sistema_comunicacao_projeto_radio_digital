"""Configuração do projeto lida de configs/*.toml (fonte única dos parâmetros).

Hoje guarda a correção de frequência do RTL-SDR adotada pela equipe
(configs/rtl.toml). Toda captura usa esse valor quando nenhum outro é pedido,
para TX, RX e calibração nunca ficarem com valores diferentes (achado A14).

Requisitos: PRC-01 (parâmetros configuráveis), CAL-01 (correção registrada).
"""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_RTL = RAIZ / "configs" / "rtl.toml"
CORRECAO_MAXIMA_PPM = 200


def ler_correcao_ppm(arquivo: Path) -> int:
    """Lê [calibracao].correcao_ppm de um arquivo TOML e valida o valor.

    Raises:
        FileNotFoundError: arquivo inexistente.
        ValueError: chave ausente, valor não inteiro ou fora de ±200 ppm.
    """
    with arquivo.open("rb") as fp:
        dados = tomllib.load(fp)
    valor = dados.get("calibracao", {}).get("correcao_ppm")
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise ValueError(f"{arquivo}: [calibracao].correcao_ppm ausente ou não inteiro")
    if abs(valor) > CORRECAO_MAXIMA_PPM:
        raise ValueError(f"{arquivo}: correção de {valor} ppm fora de ±{CORRECAO_MAXIMA_PPM}")
    return valor


@cache
def correcao_rtl_ppm_padrao() -> int:
    """Correção adotada pela equipe (configs/rtl.toml), lida uma vez por execução."""
    return ler_correcao_ppm(ARQUIVO_RTL)

"""Análise de uma sessão de bancada: os registros de cada ponto medido viram tabela e comparação.

Requisitos: MET-01 a MET-05 (métricas medidas e registradas), CMP-01 (comparação
experimental das modulações), CMP-04 (simulação × teoria × medição, com as diferenças
explicadas). Feito no bloco 20, antes da bancada, para o relatório da Etapa 5 sair dos
registros sem trabalho manual.

Cada ponto medido deixa, na pasta da sessão:
    <captura>_rx.json                  do scripts/receber.py (com --ber)
    <captura>_saida_avaliacao.json     do scripts/avaliar.py (PER e goodput)
Para cada ponto este módulo junta os dois e calcula a **perda do enlace**: quantos dB de
Eb/N0 a mais o enlace real precisou, em relação à teoria, para a BER medida. É a distância
horizontal entre o ponto e a curva teórica no gráfico BER × Eb/N0.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from sdrlink import modem, teoria

SUFIXO_RX = "_rx.json"
SUFIXO_AVALIACAO = "_saida_avaliacao.json"
BITS_MIN_BER = 10_000  # menos bits comparados que isso não dá uma BER confiável
EBN0_GRADE_DB = np.arange(-5.0, 25.0, 0.05)  # grossa: a OOK otimiza o limiar ponto a ponto
BER_MAX = 0.5  # BER de um bit no chute
BER_PISO = 1e-300  # a curva teórica chega a zero em float: piso para o log
MAX_PONTOS = 10_000


@dataclass(frozen=True)
class PontoMedido:
    """Um ponto de uma sessão de bancada.

    Attributes:
        captura: nome da captura.
        perfil: nome do perfil usado no RX.
        modulacao, fec, taxa_bits: do perfil.
        ganho_rx_db: ganho do RTL (dos metadados da gravação), se houver.
        ebn0_db: Eb/N0 medido na captura, por bit no ar.
        ber, bits_comparados: da BER com sequência conhecida (None sem --ber).
        per, goodput_bps, transmitidos: do avaliar.py (None sem a avaliação).
        banda_khz, banda_confiavel: banda a 99% medida na captura.
        offset_hz: offset residual mediano.
    """

    captura: str
    perfil: str
    modulacao: str
    fec: bool
    taxa_bits: float
    ganho_rx_db: float | None
    ebn0_db: float | None
    ber: float | None
    bits_comparados: int
    per: float | None
    goodput_bps: float | None
    transmitidos: int | None
    banda_khz: float | None
    banda_confiavel: bool | None
    offset_hz: float | None


def _numero(valor: object) -> float | None:
    """O valor como float, ou None se não for número finito (a BER sem bits comparados é NaN)."""
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(valor):
        return None
    return float(valor)


def ler_ponto(arquivo_rx: Path) -> PontoMedido:
    """Junta o registro do receber.py com o do avaliar.py (se existir) de uma captura.

    Raises:
        ValueError: arquivo que não é um registro do receber.py.
    """
    if not arquivo_rx.name.endswith(SUFIXO_RX):
        raise ValueError(f"não é um registro do receber.py: {arquivo_rx.name}")
    rx = json.loads(arquivo_rx.read_text(encoding="utf-8"))
    base = arquivo_rx.name[: -len(SUFIXO_RX)]
    arquivo_av = arquivo_rx.with_name(base + SUFIXO_AVALIACAO)
    av = json.loads(arquivo_av.read_text(encoding="utf-8")) if arquivo_av.exists() else {}
    perfil = rx.get("perfil", {})
    medidas = rx.get("medidas_da_captura", {})
    ber = rx.get("ber") or {}
    metadados = (rx.get("gravacao") or {}).get("metadados", {})
    taxa_sps = _numero(perfil.get("taxa_sps")) or 0.0
    sps = _numero(perfil.get("sps")) or 1.0
    bits_por_simbolo = modem.bits_por_simbolo_de(str(perfil.get("modulacao", "")))
    return PontoMedido(
        captura=str(rx.get("captura", base)),
        perfil=str(perfil.get("nome", "?")),
        modulacao=str(perfil.get("modulacao", "?")),
        fec=bool(perfil.get("fec", False)),
        taxa_bits=taxa_sps / sps * bits_por_simbolo,
        ganho_rx_db=_numero(metadados.get("ganho_db")),
        ebn0_db=_numero(medidas.get("ebn0_estimado_db")),
        ber=_numero(ber.get("ber")),
        bits_comparados=int(ber.get("bits_comparados", 0)),
        per=_numero(av.get("per")),
        goodput_bps=_numero(av.get("goodput_bps")),
        transmitidos=int(av["transmitidos"]) if "transmitidos" in av else None,
        banda_khz=_numero(medidas.get("banda_99_khz")),
        banda_confiavel=confiavel
        if isinstance(confiavel := medidas.get("banda_99_confiavel"), bool)
        else None,
        offset_hz=_numero(rx.get("offset_residual_mediano_hz")),
    )


def ler_sessao(pasta: Path) -> list[PontoMedido]:
    """Todos os pontos de uma pasta de sessão, em ordem de nome de captura."""
    arquivos = sorted(pasta.glob("*" + SUFIXO_RX))[:MAX_PONTOS]
    return [ler_ponto(a) for a in arquivos]


@cache
def _curva_teorica(modulacao: str) -> NDArray[np.float64]:
    """BER teórica na grade de Eb/N0, com piso para o log (calculada uma vez por modulação)."""
    ber = np.asarray(teoria.BER_TEORICA[modulacao](EBN0_GRADE_DB), dtype=np.float64)
    return np.maximum(ber, BER_PISO)


def ebn0_teorico_db(modulacao: str, ber: float) -> float | None:
    """Eb/N0 que a teoria pede para essa BER (sem código), ou None fora da curva."""
    if modulacao not in teoria.BER_TEORICA or not 0 < ber < BER_MAX:
        return None
    curva = _curva_teorica(modulacao)
    if not curva[-1] < ber < curva[0]:
        return None
    # a curva cai com o Eb/N0: interpola em log da BER, com o eixo invertido para crescer
    return float(np.interp(-np.log10(ber), -np.log10(curva), EBN0_GRADE_DB))


def perda_db(ponto: PontoMedido) -> float | None:
    """Quantos dB a mais o enlace precisou em relação à teoria, para a BER medida.

    Só sem FEC (a teoria é a da modulação sem código) e com bits suficientes.
    """
    if (
        ponto.fec
        or ponto.ber is None
        or ponto.ebn0_db is None
        or ponto.bits_comparados < BITS_MIN_BER
    ):
        return None
    teorico = ebn0_teorico_db(ponto.modulacao, ponto.ber)
    return None if teorico is None else ponto.ebn0_db - teorico


def _celula(valor: float | None, formato: str) -> str:
    """Valor formatado para a tabela, ou "sem dado"."""
    return "sem dado" if valor is None else format(valor, formato)


def tabela_markdown(pontos: list[PontoMedido]) -> str:
    """Tabela da sessão: um ponto por linha, com a perda do enlace."""
    linhas = [
        "| Captura | Perfil | Ganho RX (dB) | Eb/N0 medido (dB) | BER | PER "
        "| Goodput (kbit/s) | Banda (kHz) | Offset (Hz) | Perda (dB) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in pontos:
        banda = _celula(p.banda_khz, ".1f") + (
            "" if p.banda_confiavel in (True, None) else " (não confiável)"
        )
        goodput = None if p.goodput_bps is None else p.goodput_bps / 1e3
        per = "sem dado" if p.per is None else f"{100 * p.per:.2f}%"
        linhas.append(
            f"| {p.captura} | {p.perfil} | {_celula(p.ganho_rx_db, '.1f')} "
            f"| {_celula(p.ebn0_db, '.2f')} "
            f"| {_celula(p.ber, '.2e')} | {per} | {_celula(goodput, '.1f')} | {banda} "
            f"| {_celula(p.offset_hz, '.0f')} | {_celula(perda_db(p), '+.2f')} |"
        )
    return "\n".join(linhas) + "\n"

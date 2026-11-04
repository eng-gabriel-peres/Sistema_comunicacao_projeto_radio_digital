"""Transmissão no ADALM-Pluto (transmissor).

Requisitos: PLT-01 (Pluto só como transmissor: o receptor dele nunca é usado),
PLT-05 (frequência e potência configuradas e verificadas), CAL-01 (tom de
calibração).

Diferenças em relação ao tx_test.py da referência:
    * o buffer cíclico sempre fecha um número inteiro de ciclos do tom, então o
      espectro é uma raia única (achado A15: 102,4 ciclos viravam um pente);
    * a transmissão tem duração fixa e o buffer é sempre destruído no final,
      mesmo com Ctrl+C ou erro (se o processo morrer sem isso, o Pluto continua
      transmitindo o buffer cíclico).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import numpy as np
from numpy.typing import NDArray

URI_PADRAO = "ip:192.168.2.22"  # IP do Pluto usado nos scripts da referência
LO_MIN_HZ = 70e6  # faixa do AD9364 (Pluto Rev.C)
LO_MAX_HZ = 6e9
TAXA_MIN_SPS = 521e3
TAXA_MAX_SPS = 61.44e6
GANHO_MIN_DB = -89.75  # o ganho de TX do Pluto é uma atenuação: 0 dB é o máximo
GANHO_MAX_DB = 0.0
AMPLITUDE_PADRAO = 2**14  # metade do fundo de escala do DAC de 16 bits
N_MINIMO = 1024
N_MAXIMO = 2**20
DURACAO_MAX_S = 600.0
TOLERANCIA_CICLOS = 1e-9  # folga numérica ao conferir ciclos inteiros
TOLERANCIA_LO_HZ = 10.0  # resolução do sintetizador do AD9364 (visto: 2 Hz)


@dataclass(frozen=True)
class ConfigPluto:
    """Parâmetros de transmissão do Pluto.

    Attributes:
        lo_hz: frequência do oscilador local (centro da banda transmitida).
        taxa_sps: taxa de amostragem do DAC.
        ganho_db: ganho de TX (atenuação, de -89,75 a 0 dB).
        uri: endereço do Pluto para a libiio.
    """

    lo_hz: float
    taxa_sps: float = 2e6
    ganho_db: float = -30.0
    uri: str = URI_PADRAO

    def __post_init__(self) -> None:
        """Rejeita parâmetros fora do que o hardware aceita."""
        if not LO_MIN_HZ <= self.lo_hz <= LO_MAX_HZ:
            raise ValueError(f"LO fora da faixa do AD9364: {self.lo_hz} Hz")
        if not TAXA_MIN_SPS <= self.taxa_sps <= TAXA_MAX_SPS:
            raise ValueError(f"taxa de amostragem fora da faixa: {self.taxa_sps} S/s")
        if not GANHO_MIN_DB <= self.ganho_db <= GANHO_MAX_DB:
            raise ValueError(
                f"ganho de TX fora de {GANHO_MIN_DB} a {GANHO_MAX_DB} dB: {self.ganho_db}"
            )
        if not self.uri:
            raise ValueError("URI do Pluto vazia")


def n_amostras_ciclos_inteiros(freq_hz: float, taxa_sps: float, n_min: int = N_MINIMO) -> int:
    """Menor tamanho de buffer >= n_min em que o tom fecha um número inteiro de ciclos.

    Raises:
        ValueError: frequência ou taxa inválidas, ou buffer necessário grande demais.
    """
    if taxa_sps <= 0 or not 0 < abs(freq_hz) < taxa_sps / 2:
        raise ValueError("o tom precisa estar entre 0 e taxa/2 (em módulo)")
    razao = Fraction(round(freq_hz), round(taxa_sps)).limit_denominator(N_MAXIMO)
    q = razao.denominator  # o tom fecha ciclos inteiros a cada q amostras
    n = q * max(1, -(-n_min // q))
    if n > N_MAXIMO:
        raise ValueError(f"buffer de {n} amostras passa do limite de {N_MAXIMO}")
    return n


def tom_complexo(
    freq_hz: float, taxa_sps: float, n_amostras: int, amplitude: float = AMPLITUDE_PADRAO
) -> NDArray[np.complex64]:
    """Tom complexo exp(j2πft) com número inteiro de ciclos no buffer.

    Raises:
        ValueError: se o tom não fechar ciclos inteiros em n_amostras ou a amplitude
            passar do fundo de escala do DAC.
    """
    ciclos = freq_hz * n_amostras / taxa_sps
    if abs(ciclos - round(ciclos)) > TOLERANCIA_CICLOS:
        raise ValueError(f"{ciclos:.4f} ciclos no buffer: o tom viraria um pente de raias")
    if not 0 < amplitude < 2**15:
        raise ValueError(f"amplitude fora do fundo de escala do DAC: {amplitude}")
    t = np.arange(n_amostras) / taxa_sps
    tom: NDArray[np.complex64] = (amplitude * np.exp(2j * np.pi * freq_hz * t)).astype(np.complex64)
    return tom


def _configurar(sdr: Any, config: ConfigPluto) -> None:
    """Aplica a configuração e confere o que o rádio aceitou."""
    sdr.sample_rate = int(config.taxa_sps)
    sdr.tx_rf_bandwidth = int(config.taxa_sps)
    sdr.tx_lo = int(config.lo_hz)
    sdr.tx_hardwaregain_chan0 = config.ganho_db
    sdr.tx_cyclic_buffer = True
    if abs(int(sdr.tx_lo) - int(config.lo_hz)) > TOLERANCIA_LO_HZ:
        raise RuntimeError(f"o Pluto não aceitou o LO: pedido {config.lo_hz}, lido {sdr.tx_lo}")


def transmitir(config: ConfigPluto, amostras: NDArray[np.complex64], duracao_s: float) -> None:
    """Transmite o buffer em modo cíclico por duracao_s e desliga sempre no final.

    Raises:
        ValueError: duração inválida ou buffer vazio.
        RuntimeError: Pluto não encontrado ou configuração recusada.
    """
    if not 0 < duracao_s <= DURACAO_MAX_S:
        raise ValueError(f"duração deve ficar entre 0 e {DURACAO_MAX_S} s")
    if len(amostras) == 0:
        raise ValueError("buffer vazio")
    import adi  # noqa: PLC0415 (só carrega a libiio quando há hardware)

    try:
        sdr = adi.Pluto(config.uri)
    except Exception as erro:
        raise RuntimeError(f"não foi possível abrir o Pluto em {config.uri}: {erro}") from erro
    try:
        _configurar(sdr, config)
        sdr.tx(amostras)
        time.sleep(duracao_s)
    finally:
        sdr.tx_destroy_buffer()
        sdr.tx_hardwaregain_chan0 = GANHO_MIN_DB

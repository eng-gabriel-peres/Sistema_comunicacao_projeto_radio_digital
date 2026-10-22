"""Captura de amostras IQ no RTL-SDR (receptor).

Requisitos: PLT-01 (RTL-SDR só como receptor), MET-05 (ganho manual com AGC
desligado, registrado na captura), RX-02. Corrige o achado A8 da auditoria:
lê os bytes brutos e converte direto para complex64 (8 bytes por amostra), em
vez do complex128 do `read_samples` (16 bytes por amostra).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from sdrlink.config import correcao_rtl_ppm_padrao

FREQ_MIN_HZ = 24e6  # faixa de sintonia do R820T/R820T2
FREQ_MAX_HZ = 1766e6
TAXAS_VALIDAS_SPS = ((225_001.0, 300_000.0), (900_001.0, 3_200_000.0))
GANHO_MAX_DB = 50.0
CORRECAO_MAX_PPM = 200
AMOSTRAS_POR_LEITURA = 256 * 1024  # múltiplo de 512 bytes, exigência da librtlsdr
AMOSTRAS_DESCARTADAS = 256 * 1024  # primeiras amostras após sintonizar são instáveis
ESCALA_ADC = 127.5  # mesma escala do pyrtlsdr: (byte - 127,5) / 127,5


@dataclass(frozen=True)
class ConfigRtl:
    """Parâmetros de uma captura no RTL-SDR.

    Attributes:
        centro_hz: frequência central sintonizada.
        taxa_sps: taxa de amostragem.
        ganho_db: ganho manual do sintonizador (AGC sempre desligado).
        correcao_ppm: correção de frequência inteira aplicada pela librtlsdr; se
            omitida, vale a correção adotada em configs/rtl.toml.
    """

    centro_hz: float
    taxa_sps: float
    ganho_db: float
    correcao_ppm: int = field(default_factory=correcao_rtl_ppm_padrao)

    def __post_init__(self) -> None:
        """Rejeita parâmetros fora do que o hardware aceita."""
        if not FREQ_MIN_HZ <= self.centro_hz <= FREQ_MAX_HZ:
            raise ValueError(f"centro fora da faixa do R820T: {self.centro_hz} Hz")
        if not any(lo <= self.taxa_sps <= hi for lo, hi in TAXAS_VALIDAS_SPS):
            raise ValueError(f"taxa de amostragem não suportada: {self.taxa_sps} S/s")
        if not 0 <= self.ganho_db <= GANHO_MAX_DB:
            raise ValueError(f"ganho fora da faixa 0 a {GANHO_MAX_DB} dB: {self.ganho_db}")
        if abs(self.correcao_ppm) > CORRECAO_MAX_PPM:
            raise ValueError(f"correção fora de ±{CORRECAO_MAX_PPM} ppm: {self.correcao_ppm}")


@dataclass(frozen=True)
class Captura:
    """Amostras capturadas e os parâmetros lidos de volta do rádio."""

    amostras: NDArray[np.complex64]
    centro_hz: float
    taxa_sps: float
    ganho_db: float
    correcao_ppm: int


def bytes_para_iq(dados: NDArray[np.uint8]) -> NDArray[np.complex64]:
    """Converte bytes I,Q intercalados (0 a 255) em amostras complexas em [-1, 1].

    Raises:
        ValueError: vetor não 1-D ou com número ímpar de bytes.
    """
    if dados.ndim != 1:
        raise ValueError("os bytes devem estar em um vetor 1-D")
    if len(dados) % 2:
        raise ValueError(f"número ímpar de bytes ({len(dados)}): I e Q precisam vir em pares")
    reais = (dados.astype(np.float32) - ESCALA_ADC) / ESCALA_ADC
    iq = np.empty(len(dados) // 2, dtype=np.complex64)
    iq.real = reais[0::2]
    iq.imag = reais[1::2]
    return iq


def fracao_saturada(amostras: NDArray[np.complex64]) -> float:
    """Fração de amostras com I ou Q no fundo de escala do ADC de 8 bits.

    Acima de cerca de 0,1% o ganho está alto demais e o sinal fica distorcido.

    Raises:
        ValueError: vetor vazio.
    """
    if len(amostras) == 0:
        raise ValueError("vetor de amostras vazio")
    limite = (ESCALA_ADC - 1) / ESCALA_ADC
    no_limite = (np.abs(amostras.real) >= limite) | (np.abs(amostras.imag) >= limite)
    return float(np.mean(no_limite))


def _configurar(radio: Any, config: ConfigRtl) -> None:
    """Aplica a configuração. A correção só é gravada se mudar.

    A librtlsdr devolve erro quando o ppm pedido é igual ao atual, e o pyrtlsdr
    fecha o rádio nesse caso; por isso a comparação antes de gravar.
    """
    radio.sample_rate = config.taxa_sps
    radio.center_freq = config.centro_hz
    radio.gain = config.ganho_db  # ganho manual: desliga o AGC do sintonizador
    radio.set_agc_mode(False)  # AGC digital do RTL2832U desligado
    if int(radio.get_freq_correction()) != config.correcao_ppm:
        radio.freq_correction = config.correcao_ppm


def _ler(radio: Any, n_amostras: int) -> NDArray[np.complex64]:
    """Lê n_amostras em blocos de tamanho fixo, num vetor pré-alocado."""
    amostras = np.empty(n_amostras, dtype=np.complex64)
    for i in range(n_amostras // AMOSTRAS_POR_LEITURA):  # laço com limite fixo
        bruto = np.frombuffer(radio.read_bytes(2 * AMOSTRAS_POR_LEITURA), dtype=np.uint8)
        if len(bruto) != 2 * AMOSTRAS_POR_LEITURA:
            raise RuntimeError(f"leitura incompleta do RTL-SDR: {len(bruto)} bytes")
        inicio = i * AMOSTRAS_POR_LEITURA
        amostras[inicio : inicio + AMOSTRAS_POR_LEITURA] = bytes_para_iq(bruto)
    return amostras


def capturar(config: ConfigRtl, n_amostras: int) -> Captura:
    """Configura o RTL-SDR, descarta o início e captura n_amostras.

    Args:
        config: parâmetros da captura.
        n_amostras: quantidade de amostras, múltipla de AMOSTRAS_POR_LEITURA.

    Raises:
        ValueError: n_amostras inválido.
        RuntimeError: rádio ocupado, ausente ou leitura incompleta.
    """
    if n_amostras <= 0 or n_amostras % AMOSTRAS_POR_LEITURA:
        raise ValueError(f"n_amostras deve ser múltiplo positivo de {AMOSTRAS_POR_LEITURA}")
    from rtlsdr import RtlSdr  # noqa: PLC0415 (só carrega a librtlsdr quando há captura)

    try:
        radio = RtlSdr()
    except OSError as erro:
        raise RuntimeError(
            "não foi possível abrir o RTL-SDR: ele está desconectado ou outro programa "
            f"(teste_FM.py, SDR#, SDR++) está usando o rádio. Detalhe: {erro}"
        ) from erro
    try:
        _configurar(radio, config)
        radio.read_bytes(2 * AMOSTRAS_DESCARTADAS)
        amostras = _ler(radio, n_amostras)
        return Captura(
            amostras=amostras,
            centro_hz=float(radio.center_freq),
            taxa_sps=float(radio.sample_rate),
            ganho_db=float(radio.gain),
            correcao_ppm=int(radio.get_freq_correction()),
        )
    finally:
        radio.close()

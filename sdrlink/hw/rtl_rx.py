"""Captura de amostras IQ no RTL-SDR (receptor).

Requisitos: PLT-01 (RTL-SDR só como receptor), MET-05 (ganho manual com AGC
desligado, registrado na captura), RX-02. Corrige o achado A8 da auditoria:
lê os bytes brutos e converte direto para complex64 (8 bytes por amostra), em
vez do complex128 do `read_samples` (16 bytes por amostra). Corrige também o
achado A17: a leitura é assíncrona e contínua, sem perder amostras entre blocos.
"""

from __future__ import annotations

import threading
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
MARGEM_TEMPO_S = 5.0  # folga do tempo máximo de uma captura


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


class Acumulador:
    """Recebe os blocos da leitura assíncrona e os copia, em ordem, num vetor pré-alocado.

    A leitura síncrona bloco a bloco (`read_bytes` em laço, como no
    capture_chunks da referência) perde de 1 a 6 mil amostras em cada emenda
    de bloco: medido em 04/11/2026, cerca de 1,5% a 4% das amostras (achado A17).
    Na leitura assíncrona a librtlsdr mantém vários buffers USB em fila e o
    fluxo é contínuo; este objeto é o callback que guarda cada bloco.
    """

    def __init__(self, radio: Any, n_bytes: int, n_bytes_descarte: int) -> None:
        """Prepara o destino.

        Raises:
            ValueError: tamanhos inválidos.
        """
        if n_bytes <= 0 or n_bytes % 2 or n_bytes_descarte < 0:
            raise ValueError("tamanhos de leitura inválidos")
        self.radio = radio
        self.dados = np.empty(n_bytes, dtype=np.uint8)
        self.pos = -n_bytes_descarte  # posição negativa: ainda descartando o início
        self.cancelado = False

    @property
    def completo(self) -> bool:
        """True quando o vetor de destino está cheio."""
        return self.pos >= len(self.dados)

    def __call__(self, valores: Any, _contexto: Any) -> None:
        """Copia um bloco (o buffer da librtlsdr é reaproveitado, então copia na hora)."""
        if self.completo:
            return
        bloco = np.frombuffer(valores, dtype=np.uint8)
        inicio = 0
        if self.pos < 0:  # ainda dentro do descarte inicial
            inicio = min(len(bloco), -self.pos)
            self.pos += inicio
        n = min(len(bloco) - inicio, len(self.dados) - max(self.pos, 0))
        if n > 0:
            self.dados[self.pos : self.pos + n] = bloco[inicio : inicio + n]
            self.pos += n
        if self.pos >= len(self.dados) and not self.cancelado:  # comparação direta
            self.cancelado = True
            self.radio.cancel_read_async()


def _ler(radio: Any, n_amostras: int, taxa_sps: float) -> NDArray[np.complex64]:
    """Lê n_amostras contínuas pela leitura assíncrona, com tempo máximo de segurança.

    Ao cancelar, a librtlsdr devolve o resultado do último libusb_cancel_transfer,
    que é LIBUSB_ERROR_NOT_FOUND quando a transferência já tinha terminado; o
    pyrtlsdr transforma isso em exceção (e fecha o rádio). Com o vetor cheio esse
    erro é só o fim normal da leitura e é ignorado.

    Raises:
        RuntimeError: leitura incompleta (tempo de segurança esgotado ou erro USB).
    """
    acumulador = Acumulador(radio, 2 * n_amostras, 2 * AMOSTRAS_DESCARTADAS)
    limite_s = 2 * (n_amostras + AMOSTRAS_DESCARTADAS) / taxa_sps + MARGEM_TEMPO_S
    vigia = threading.Timer(limite_s, radio.cancel_read_async)  # regra 2: termina sempre
    vigia.start()
    erro_usb: OSError | None = None
    try:
        radio.read_bytes_async(acumulador, 2 * AMOSTRAS_POR_LEITURA)
    except OSError as erro:  # LibUSBError herda de IOError
        erro_usb = erro
    finally:
        vigia.cancel()
    if not acumulador.completo:
        raise RuntimeError(
            f"leitura incompleta do RTL-SDR: {max(acumulador.pos, 0)} bytes"
        ) from erro_usb
    return bytes_para_iq(acumulador.dados)


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
        # lidos antes da captura: o pyrtlsdr pode fechar o rádio ao fim da leitura assíncrona
        centro_hz = float(radio.center_freq)
        taxa_sps = float(radio.sample_rate)
        ganho_db = float(radio.gain)
        correcao_ppm = int(radio.get_freq_correction())
        amostras = _ler(radio, n_amostras, config.taxa_sps)
        return Captura(amostras, centro_hz, taxa_sps, ganho_db, correcao_ppm)
    finally:
        radio.close()

"""Calibração de frequência do RTL-SDR a partir de um tom conhecido.

O Pluto transmite um tom em frequência conhecida; o RTL-SDR mede onde o tom
realmente chegou. A diferença dá o erro de frequência em ppm, a correção
inteira que a librtlsdr aceita e o resíduo que sobra depois dela.

Requisitos: CAL-01 (ppm calibrado e registrado), CAL-02 (offset residual medido).
Corrige os achados da auditoria: A5 (a correção é calculada a partir de uma
captura sem correção), A6 (resolução de cerca de 2 Hz em vez de 500 Hz) e A7
(o erro é tratado como relativo entre Pluto e RTL, não absoluto).

Convenção de sinal:
    erro_ppm = (f_medida - f_esperada) / f_esperada * 1e6.
    Um cristal do RTL rápido em +e ppm sobe o oscilador local e faz o tom
    aparecer abaixo do esperado (erro = -e). A librtlsdr corrige um cristal
    rápido com freq_correction = +e, logo correção = round(-erro_ppm).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks

N_FFT_PADRAO = 2**20
SNR_MINIMA_DB = 10.0  # sobre o piso do espectro médio (ruído liso)
MARGEM_AMBIGUIDADE_DB = 3.0  # 2ª raia mais perto que isso: não dá para escolher
JANELA_FINA_HZ = 100.0  # estimativa por bloco só perto da raia detectada
SEPARACAO_RAIAS_HZ = 200.0
BINS_MINIMOS_BUSCA = 3  # menos que isso não forma um pico
N_FFT_MINIMO = 1024
ERRO_MAXIMO_PPM = 200.0  # cristais comuns ficam bem abaixo disso
PPM = 1e6


@dataclass(frozen=True)
class EstimativaTom:
    """Frequência estimada de um tom em banda base.

    Attributes:
        freq_hz: frequência do tom relativa ao centro sintonizado, em Hz.
        snr_db: potência do pico sobre a mediana do ruído na janela de busca.
        resolucao_hz: largura de um bin da FFT usada.
    """

    freq_hz: float
    snr_db: float
    resolucao_hz: float


@dataclass(frozen=True)
class Raia:
    """Raia detectada no espectro médio.

    Attributes:
        freq_hz: frequência em banda base, em Hz.
        snr_db: altura sobre a mediana do espectro médio na janela de busca.
    """

    freq_hz: float
    snr_db: float


@dataclass(frozen=True)
class Estatistica:
    """Resumo de várias estimativas consecutivas do mesmo tom.

    Attributes:
        media_hz: frequência média em banda base.
        desvio_hz: desvio padrão entre as estimativas.
        deriva_hz_s: inclinação da reta frequência × tempo (deriva térmica).
        snr_min_db: pior SNR entre as estimativas.
        n: número de estimativas.
    """

    media_hz: float
    desvio_hz: float
    deriva_hz_s: float
    snr_min_db: float
    n: int


def _validar_busca(
    amostras: NDArray[np.complex64], taxa_sps: float, freq_busca_hz: float, janela_busca_hz: float
) -> None:
    """Confere os argumentos comuns das funções de estimativa."""
    if amostras.ndim != 1:
        raise ValueError("as amostras devem ser um vetor 1-D")
    if taxa_sps <= 0:
        raise ValueError(f"taxa de amostragem inválida: {taxa_sps}")
    if janela_busca_hz <= 0:
        raise ValueError(f"janela de busca inválida: {janela_busca_hz}")
    if abs(freq_busca_hz) + janela_busca_hz >= taxa_sps / 2:
        raise ValueError("a janela de busca ultrapassa a banda amostrada (±taxa/2)")


def _interpolar_pico(potencia: NDArray[np.float64], k: int) -> float:
    """Desvio fracionário do pico (em bins) por parábola no log da potência."""
    n = len(potencia)
    a, b, c = (10 * np.log10(potencia[(k + d) % n] + 1e-30) for d in (-1, 0, 1))
    denominador = a - 2 * b + c
    if denominador >= 0:  # não é um máximo local: fica no bin inteiro
        return 0.0
    return float(np.clip(0.5 * (a - c) / denominador, -0.5, 0.5))


def estimar_tom(
    amostras: NDArray[np.complex64],
    taxa_sps: float,
    freq_busca_hz: float,
    janela_busca_hz: float,
    n_fft: int = N_FFT_PADRAO,
) -> EstimativaTom:
    """Estima a frequência de um tom com FFT janelada e interpolação do pico.

    Usa as primeiras `n_fft` amostras. Com 2,048 MS/s e n_fft = 2**20 a
    resolução é de 1,95 Hz e a interpolação leva o erro a uma fração disso.

    Args:
        amostras: IQ complexo em banda base.
        taxa_sps: taxa de amostragem, em amostras por segundo.
        freq_busca_hz: frequência em banda base onde o tom é esperado.
        janela_busca_hz: meia largura da faixa de busca em torno de freq_busca_hz.
        n_fft: tamanho da FFT (potência de 2).

    Raises:
        ValueError: argumentos fora da faixa ou amostras insuficientes.
    """
    _validar_busca(amostras, taxa_sps, freq_busca_hz, janela_busca_hz)
    if n_fft < N_FFT_MINIMO or n_fft & (n_fft - 1):
        raise ValueError(f"n_fft deve ser potência de 2 e >= {N_FFT_MINIMO}: {n_fft}")
    if len(amostras) < n_fft:
        raise ValueError(f"amostras insuficientes: {len(amostras)} < n_fft = {n_fft}")
    segmento = amostras[:n_fft].astype(np.complex128)
    segmento -= segmento.mean()  # tira o DC do RTL-SDR
    potencia = np.abs(np.fft.fft(segmento * np.hanning(n_fft))) ** 2
    freqs = np.fft.fftfreq(n_fft, 1 / taxa_sps)
    indices = np.flatnonzero(np.abs(freqs - freq_busca_hz) <= janela_busca_hz)
    k = int(indices[np.argmax(potencia[indices])])
    resolucao_hz = taxa_sps / n_fft
    freq_hz = float(freqs[k]) + _interpolar_pico(potencia, k) * resolucao_hz
    snr_db = float(10 * np.log10(potencia[k] / np.median(potencia[indices])))
    return EstimativaTom(freq_hz, snr_db, resolucao_hz)


def estimar_por_blocos(
    amostras: NDArray[np.complex64],
    taxa_sps: float,
    freq_busca_hz: float,
    janela_busca_hz: float,
    n_fft: int = N_FFT_PADRAO,
) -> list[EstimativaTom]:
    """Divide a captura em blocos de `n_fft` amostras e estima o tom em cada um.

    Raises:
        ValueError: se a captura não tiver pelo menos um bloco completo.
    """
    n_blocos = len(amostras) // n_fft
    if n_blocos < 1:
        raise ValueError(f"captura menor que um bloco de {n_fft} amostras")
    return [
        estimar_tom(
            amostras[i * n_fft : (i + 1) * n_fft], taxa_sps, freq_busca_hz, janela_busca_hz, n_fft
        )
        for i in range(n_blocos)
    ]


def resumir(estimativas: list[EstimativaTom], duracao_bloco_s: float) -> Estatistica:
    """Calcula média, desvio, deriva e pior SNR de estimativas consecutivas.

    Raises:
        ValueError: lista vazia ou duração de bloco não positiva.
    """
    if not estimativas:
        raise ValueError("nenhuma estimativa para resumir")
    if duracao_bloco_s <= 0:
        raise ValueError(f"duração de bloco inválida: {duracao_bloco_s}")
    freqs = np.array([e.freq_hz for e in estimativas])
    n = len(freqs)
    desvio = float(freqs.std(ddof=1)) if n > 1 else 0.0
    deriva = float(np.polyfit(np.arange(n) * duracao_bloco_s, freqs, 1)[0]) if n > 1 else 0.0
    snr_min = min(e.snr_db for e in estimativas)
    return Estatistica(float(freqs.mean()), desvio, deriva, snr_min, n)


def erro_ppm(freq_medida_hz: float, freq_esperada_hz: float) -> float:
    """Erro relativo de frequência, em ppm (positivo: chegou acima do esperado).

    Raises:
        ValueError: frequência esperada não positiva.
    """
    if freq_esperada_hz <= 0:
        raise ValueError(f"frequência esperada inválida: {freq_esperada_hz}")
    return (freq_medida_hz - freq_esperada_hz) / freq_esperada_hz * PPM


def correcao_rtl_ppm(erro: float) -> int:
    """Correção inteira para o freq_correction da librtlsdr (ver convenção no topo).

    Raises:
        ValueError: erro fora da faixa plausível de ±200 ppm.
    """
    if abs(erro) > ERRO_MAXIMO_PPM:
        raise ValueError(
            f"erro de {erro:.1f} ppm fora da faixa plausível (±{ERRO_MAXIMO_PPM:.0f} ppm)"
        )
    return round(-erro)


def residuo_previsto_hz(erro: float, correcao: int, freq_hz: float) -> float:
    """Offset que sobra depois de aplicar a correção inteira, em Hz.

    Como a librtlsdr só aceita ppm inteiro, sobra até ±0,5 ppm: cerca de
    ±457 Hz em 915 MHz. Esse é o "offset residual de centenas de Hz" do enunciado.

    Raises:
        ValueError: frequência não positiva.
    """
    if freq_hz <= 0:
        raise ValueError(f"frequência inválida: {freq_hz}")
    return (erro + correcao) * freq_hz / PPM


def espectro_medio(
    amostras: NDArray[np.complex64], taxa_sps: float, n_fft: int = N_FFT_PADRAO
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Média dos periodogramas (janela de Hann) de blocos consecutivos de n_fft amostras.

    A média deixa o ruído liso, então uma raia fraca mas estável se destaca de
    flutuações do ruído e de interferentes intermitentes.

    Raises:
        ValueError: taxa inválida ou captura menor que um bloco.
    """
    if taxa_sps <= 0:
        raise ValueError(f"taxa de amostragem inválida: {taxa_sps}")
    n_blocos = len(amostras) // n_fft
    if n_blocos < 1:
        raise ValueError(f"captura menor que um bloco de {n_fft} amostras")
    janela = np.hanning(n_fft)
    acumulado = np.zeros(n_fft)
    for i in range(n_blocos):  # laço com limite fixo
        bloco = amostras[i * n_fft : (i + 1) * n_fft].astype(np.complex128)
        bloco -= bloco.mean()
        acumulado += np.abs(np.fft.fft(bloco * janela)) ** 2
    return np.fft.fftfreq(n_fft, 1 / taxa_sps), acumulado / n_blocos


def detectar_raias(
    freqs: NDArray[np.float64],
    potencia: NDArray[np.float64],
    freq_busca_hz: float,
    janela_busca_hz: float,
    n_max: int = 3,
) -> list[Raia]:
    """Lista as raias mais fortes da janela de busca, da mais forte para a mais fraca.

    Raises:
        ValueError: vetores de tamanhos diferentes, janela vazia ou n_max < 1.
    """
    if freqs.shape != potencia.shape:
        raise ValueError("freqs e potencia precisam ter o mesmo tamanho")
    if n_max < 1:
        raise ValueError(f"n_max deve ser >= 1: {n_max}")
    indices = np.flatnonzero(np.abs(freqs - freq_busca_hz) <= janela_busca_hz)
    if len(indices) < BINS_MINIMOS_BUSCA:
        raise ValueError("janela de busca sem bins suficientes")
    db = 10 * np.log10(potencia[indices] / np.median(potencia[indices]))
    resolucao_hz = abs(float(freqs[1] - freqs[0]))
    picos, _ = find_peaks(db, distance=max(1, int(SEPARACAO_RAIAS_HZ / resolucao_hz)))
    melhores = picos[np.argsort(db[picos])[::-1][:n_max]]
    return [Raia(float(freqs[indices[k]]), float(db[k])) for k in melhores]

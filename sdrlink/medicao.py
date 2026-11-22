"""Medidas tiradas da captura: banda ocupada a 99% e Eb/N0 estimado.

Requisitos: MET-04 (banda a 99% pela DEP medida no RTL-SDR), MET-05 (registro do
ensaio) e a comparação simulação × medição da Etapa 5, que precisa do Eb/N0 real.

Medir direto na captura daria números errados: o ruído dos 2 MHz entra nos 99%
da potência, o pico de DC do RTL também, e o resultado mudaria com o ganho. Por
isso as duas medidas usam a diferença entre a densidade espectral do trecho com
sinal e a de um trecho só com ruído da mesma captura (o RX começa a gravar antes
de o TX começar a transmitir):

    banda:  99% da potência de S_sinal(f) - S_ruido(f);
    Eb/N0:  P_sinal = integral de S_sinal - S_ruido; N0 = média de S_ruido dentro
            da banda do sinal; Eb/N0 = P_sinal / (N0 · Rb).

A diferença não é cortada em zero: fora da banda ela flutua em torno de zero e as
flutuações se cancelam na soma. Cortar os negativos deixava só as positivas, que,
somadas nos milhares de frequências sem sinal, alargavam a banda medida (1,6 MHz
em vez de 298 kHz na validação de 21/11/2026).

O Eb/N0 assim definido é o mesmo da simulação (sdrlink.canal): energia média por
bit sobre a densidade do ruído na banda do sinal.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from sdrlink import espectro

NPERSEG = 4096
AMOSTRAS_MIN = 4 * NPERSEG  # cada trecho precisa de alguns segmentos de Welch
MARGEM_S = 1e-3  # o ruído termina 1 ms antes do primeiro quadro
SINAL_MAX = 2**22  # amostras de sinal usadas (cerca de 2 s): mais não muda a média
# Ruído mínimo antes do 1º quadro. Medido em 21/11/2026 (DBPSK 256 kbit/s, 5 sementes):
# com 49 ms a banda errou até 33% e o Eb/N0 até 1,1 dB a 8 dB; com 122 ms, até 2,7% e
# 0,03 dB; com 244 ms ou mais, abaixo de 2% e 0,05 dB. 0,2 s dá folga sobre os 122 ms.
RUIDO_MIN_S = 0.2
# Abaixo disso a banda a 99% medida não é confiável. Medido no bloco 13 com o perfil
# prova-b (sinal de 30 kHz em 2,048 MS/s): -13 dB deu 1884 kHz, -9 dB deu 764 kHz,
# -4 dB deu 30,9 kHz. O resíduo da subtração do ruído, somado em 2 MHz, passa da
# potência do sinal.
SNR_MIN_BANDA_DB = -5.0


def _densidades(
    sinal: NDArray[np.complexfloating], ruido: NDArray[np.complexfloating], taxa_sps: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Frequências, DEP do sinal menos a do ruído (sem cortar negativos) e DEP do ruído.

    Raises:
        ValueError: trecho curto demais.
    """
    if min(len(sinal), len(ruido)) < AMOSTRAS_MIN:
        raise ValueError(f"trechos precisam de pelo menos {AMOSTRAS_MIN} amostras")
    f, s_sinal = espectro.densidade(sinal, taxa_sps, NPERSEG)
    _, s_ruido = espectro.densidade(ruido, taxa_sps, NPERSEG)
    return f, s_sinal - s_ruido, s_ruido


def _limites(f: NDArray[np.float64], liquida: NDArray[np.float64]) -> tuple[float, float]:
    """Faixa com espectro.FRACAO_PADRAO (99%) da potência, metade do resto de cada lado.

    Raises:
        ValueError: sem potência acima do ruído.
    """
    total = float(np.sum(liquida))
    if total <= 0:
        raise ValueError("o trecho de sinal não tem potência acima do ruído")
    acumulada = np.cumsum(liquida) / total
    fora = (1 - espectro.FRACAO_PADRAO) / 2  # a mesma fração de sdrlink.espectro
    return float(np.interp(fora, acumulada, f)), float(np.interp(1 - fora, acumulada, f))


def banda_99_medida(
    sinal: NDArray[np.complexfloating], ruido: NDArray[np.complexfloating], taxa_sps: float
) -> tuple[float, float]:
    """Limites (Hz, em relação ao centro da captura) da faixa com 99% da potência do sinal.

    Raises:
        ValueError: trecho curto demais ou sem potência acima do ruído.
    """
    f, liquida, _ = _densidades(sinal, ruido, taxa_sps)
    return _limites(f, liquida)


def ebn0_estimado_db(
    sinal: NDArray[np.complexfloating],
    ruido: NDArray[np.complexfloating],
    taxa_sps: float,
    taxa_bits: float,
) -> float:
    """Eb/N0 (dB) do trecho de sinal, com N0 medido no trecho de ruído, dentro da banda do sinal.

    Raises:
        ValueError: trecho curto demais, sem potência ou taxa de bits inválida.
    """
    if taxa_bits <= 0:
        raise ValueError(f"taxa de bits inválida: {taxa_bits}")
    f, liquida, s_ruido = _densidades(sinal, ruido, taxa_sps)
    baixo, alto = _limites(f, liquida)
    na_banda = (f >= baixo) & (f <= alto)
    potencia = float(np.sum(liquida)) * taxa_sps / NPERSEG
    n0 = float(np.mean(s_ruido[na_banda]))
    return float(10 * np.log10(potencia / (n0 * taxa_bits)))


def medir_captura(
    x: NDArray[np.complexfloating],
    inicio_sinal: float,
    fim_sinal: float,
    taxa_sps: float,
    taxa_bits: float,
) -> dict[str, object]:
    """Banda a 99% e Eb/N0: ruído antes do primeiro quadro, sinal do primeiro quadro ao fim.

    Deixa uma margem de 1 ms antes do primeiro quadro (cauda do filtro, incerteza
    do instante) e usa no máximo SINAL_MAX amostras de sinal. Quando não há ruído
    suficiente antes do primeiro quadro, devolve o motivo em vez das medidas.

    Registra também a SNR na banda inteira da captura. Com sinal estreito e fraco (a
    prova B no alcance máximo) ela fica muito negativa, e a banda medida perde o
    sentido: "banda_99_confiavel" fica falso. A banda não muda com a distância; nesse
    caso, medir na posição mais próxima.
    """
    fim_ruido = int(inicio_sinal - MARGEM_S * taxa_sps)
    if fim_ruido < RUIDO_MIN_S * taxa_sps:
        return {
            "medido": False,
            "motivo": f"menos de {RUIDO_MIN_S} s de ruído antes do 1º quadro (gravar antes do TX)",
        }
    comeco = int(np.ceil(inicio_sinal))
    trecho = np.asarray(x[comeco : min(int(fim_sinal), comeco + SINAL_MAX)])
    ruido = np.asarray(x[:fim_ruido])
    if len(trecho) < AMOSTRAS_MIN:
        return {"medido": False, "motivo": f"menos de {AMOSTRAS_MIN} amostras de sinal"}
    baixo, alto = banda_99_medida(trecho, ruido, taxa_sps)
    potencia_ruido = float(np.mean(np.abs(ruido) ** 2))
    potencia_sinal = max(float(np.mean(np.abs(trecho) ** 2)) - potencia_ruido, np.finfo(float).tiny)
    snr_db = float(10 * np.log10(potencia_sinal / potencia_ruido))
    return {
        "medido": True,
        "banda_99_khz": round((alto - baixo) / 1e3, 1),
        "banda_99_limites_khz": [round(baixo / 1e3, 1), round(alto / 1e3, 1)],
        "snr_na_captura_db": round(snr_db, 1),
        "banda_99_confiavel": snr_db >= SNR_MIN_BANDA_DB,
        "ebn0_estimado_db": round(ebn0_estimado_db(trecho, ruido, taxa_sps, taxa_bits), 2),
        "amostras_de_ruido": len(ruido),
        "amostras_de_sinal": len(trecho),
    }


TOLERANCIA_PLANA_DB = 1.0
FAIXA_REFERENCIA = 0.2  # a referência do piso é a mediana em ±20% da metade da taxa
LARGURA_MEDIANA = 15  # pontos da DEP na mediana móvel (o piso de ruído é irregular)


def faixa_plana(
    ruido: NDArray[np.complexfloating], taxa_sps: float, tolerancia_db: float = TOLERANCIA_PLANA_DB
) -> tuple[float, float]:
    """Faixa em que o piso de ruído do RTL não cai mais que tolerancia_db abaixo do centro.

    É a resposta em frequência do receptor vista pelo ruído: o filtro anti-aliasing
    derruba as bordas. Os perfis põem o sinal dentro dessa faixa (bloco 07: ±850 kHz a
    2,048 MS/s). Só a queda conta: a resposta do nosso RTL tem uma elevação de +1 dB
    perto de ±650 kHz, que não atrapalha o sinal. A referência é a mediana do piso perto
    do centro, sem o pico de DC; a DEP passa por uma mediana móvel antes da comparação.
    Captura com o Pluto desligado: um sinal na faixa vira um degrau e confunde a medida.
    Devolve (baixo, alto) em Hz: as frequências mais afastadas do centro, de cada lado,
    ainda dentro da tolerância.

    Raises:
        ValueError: captura curta demais.
    """
    if len(ruido) < AMOSTRAS_MIN:
        raise ValueError(f"a captura precisa de pelo menos {AMOSTRAS_MIN} amostras")
    f, dep = espectro.densidade(np.asarray(ruido) - np.mean(ruido), taxa_sps, NPERSEG)
    db = 10 * np.log10(np.maximum(dep, np.finfo(float).tiny))
    meio = LARGURA_MEDIANA // 2
    janelas = np.lib.stride_tricks.sliding_window_view(
        np.pad(db, meio, mode="edge"), LARGURA_MEDIANA
    )
    suave = np.median(janelas, axis=1)
    perto = (np.abs(f) < FAIXA_REFERENCIA * taxa_sps / 2) & (np.abs(f) > 2 * taxa_sps / NPERSEG)
    referencia = float(np.median(suave[perto]))
    dentro = suave >= referencia - tolerancia_db
    centro = int(np.argmin(np.abs(f)))
    alto = centro
    while alto + 1 < len(f) and dentro[alto + 1]:
        alto += 1
    baixo = centro
    while baixo - 1 >= 0 and dentro[baixo - 1]:
        baixo -= 1
    return float(f[baixo]), float(f[alto])

"""Moduladores e demoduladores em banda base: OOK, BPSK, DBPSK e 2-FSK.

Requisitos: MOD-01 a MOD-03 (OOK, 2-FSK e BPSK implementados pela equipe),
PUL-01 (pulso retangular e alternativas).

Um bit por símbolo em todas as modulações. O sinal é complexo, em banda base,
com sps amostras por símbolo; o deslocamento para a frequência de transmissão
fica a cargo do TX. Os demoduladores deste módulo supõem o instante de
amostragem conhecido (sincronismo ideal): estimar tempo, fase e offset a partir
do preâmbulo é tarefa do receptor (sub-bloco 3c).

    OOK   amplitudes 0/1, detecção não coerente (módulo) com limiar entre os dois níveis
    BPSK  amplitudes -1/+1, detecção coerente (precisa da fase da portadora)
    DBPSK bit 1 = inversão de fase; detecção diferencial, não precisa da fase
    2-FSK fase contínua, tons em +-h*Rb/2; detecção não coerente por correlação
          com os dois tons (ortogonais com h = 1)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sdrlink import pulsos

Bits = NDArray[np.uint8]
Sinal = NDArray[np.complex128]

MODULACOES = ("ook", "bpsk", "dbpsk", "fsk")
PULSOS_LINEARES = ("retangular", "rrc")  # OOK, BPSK, DBPSK: pulso de símbolo
PULSOS_FSK = ("retangular", "gaussiano")  # 2-FSK: pulso de frequência
ITERACOES_LIMIAR = 20
H_MAX = 2.0  # índice de modulação máximo aceito


@dataclass(frozen=True)
class ConfigModem:
    """Escolha da modulação e do pulso.

    Attributes:
        modulacao: "ook", "bpsk", "dbpsk" ou "fsk".
        pulso: "retangular" ou "rrc" (lineares); "retangular" ou "gaussiano" (fsk).
        sps: amostras por símbolo.
        beta: fator de rolagem do RRC.
        bt: produto banda-tempo do pulso gaussiano.
        h: índice de modulação da 2-FSK (desvio de pico = h * Rb / 2).
        span: duração dos pulsos RRC e gaussiano, em símbolos.
    """

    modulacao: str
    pulso: str
    sps: int
    beta: float = 0.35
    bt: float = 0.5
    h: float = 1.0
    span: int = 12  # RRC truncado em 8 símbolos deixa 3,4% de ISI no pico; em 12, 0,4%

    def __post_init__(self) -> None:
        """Rejeita combinações inválidas.

        Raises:
            ValueError: modulação, pulso ou índice de modulação inválidos.
        """
        if self.modulacao not in MODULACOES:
            raise ValueError(f"modulação desconhecida: {self.modulacao}")
        validos = PULSOS_FSK if self.modulacao == "fsk" else PULSOS_LINEARES
        if self.pulso not in validos:
            raise ValueError(f"pulso {self.pulso} não serve para {self.modulacao}: use {validos}")
        if not 0 < self.h <= H_MAX:
            raise ValueError(f"índice de modulação fora de (0, 2]: {self.h}")
        self.formato()  # valida sps, beta, bt e span

    def formato(self) -> NDArray[np.float64]:
        """Pulso de símbolo (lineares) ou de frequência (fsk)."""
        if self.pulso == "rrc":
            return pulsos.rrc(self.beta, self.sps, self.span)
        if self.pulso == "gaussiano":
            return pulsos.gaussiano(self.bt, self.sps, self.span)
        if self.modulacao == "fsk":
            return np.ones(self.sps)  # pulso de frequência retangular: CPFSK
        return pulsos.retangular(self.sps)


def _impulsos(simbolos: NDArray[np.float64], sps: int) -> NDArray[np.float64]:
    """Um impulso por símbolo, a cada sps amostras."""
    trem = np.zeros(len(simbolos) * sps)
    trem[::sps] = simbolos
    return trem


def _simbolos_lineares(bits: Bits, modulacao: str) -> NDArray[np.float64]:
    """Amplitudes dos símbolos de OOK, BPSK e DBPSK (DBPSK ganha um símbolo de referência)."""
    b = bits.astype(np.float64)
    if modulacao == "ook":
        return b
    if modulacao == "bpsk":
        return 2 * b - 1
    return np.cumprod(np.concatenate([[1.0], 1 - 2 * b]))  # dbpsk: bit 1 inverte a fase


def modular(bits: Bits, config: ConfigModem) -> Sinal:
    """Sinal complexo em banda base para a sequência de bits.

    Raises:
        ValueError: bits vazios ou com valores diferentes de 0 e 1.
    """
    if len(bits) == 0 or np.any(bits > 1):
        raise ValueError("os bits devem ser uma sequência não vazia de 0 e 1")
    forma = config.formato()
    if config.modulacao == "fsk":
        frequencia = np.convolve(_impulsos(2 * bits.astype(np.float64) - 1, config.sps), forma)
        # fase(n) = integral da frequência até n, exclusive (pi*h por símbolo); com a soma
        # inclusiva a fase ficava adiantada 1 amostra, e o alinhamento dependia da taxa
        fase = np.concatenate([[0.0], np.cumsum(frequencia)[:-1]]) * np.pi * config.h / config.sps
        return np.exp(1j * fase)
    simbolos = _simbolos_lineares(bits, config.modulacao)
    return np.convolve(_impulsos(simbolos, config.sps), forma).astype(np.complex128)


def _limiar_dois_niveis(valores: NDArray[np.float64]) -> float:
    """Limiar entre os dois grupos de valores (k-médias com k = 2, número fixo de iterações)."""
    limiar = (float(np.min(valores)) + float(np.max(valores))) / 2
    for _ in range(ITERACOES_LIMIAR):
        altos, baixos = valores[valores > limiar], valores[valores <= limiar]
        if len(altos) == 0 or len(baixos) == 0:
            break
        limiar = float(altos.mean() + baixos.mean()) / 2
    return limiar


def saida_casada(amostras: Sinal, config: ConfigModem, n_simbolos: int) -> Sinal:
    """Saída do filtro casado no instante ótimo de cada símbolo (OOK, BPSK, DBPSK).

    Raises:
        ValueError: sinal curto demais para n_simbolos.
    """
    forma = config.formato()
    casado = np.convolve(amostras, forma[::-1])
    instantes = np.arange(n_simbolos) * config.sps + len(forma) - 1
    if instantes[-1] >= len(casado):
        raise ValueError("sinal curto demais para a quantidade de bits pedida")
    return casado[instantes]


def _demodular_fsk(amostras: Sinal, config: ConfigModem, n_bits: int) -> Bits:
    """Correlação não coerente com os dois tons, numa janela de um símbolo por bit.

    Raises:
        ValueError: sinal curto demais para n_bits.
    """
    sps = config.sps
    centro = (len(config.formato()) - 1) / 2 - (sps - 1) / 2  # atraso do pulso de frequência
    inicios = np.arange(n_bits) * sps + round(centro)
    if inicios[-1] + sps > len(amostras):
        raise ValueError("sinal curto demais para a quantidade de bits pedida")
    janelas = amostras[inicios[:, None] + np.arange(sps)]
    giro = np.exp(-1j * np.pi * config.h * np.arange(sps) / sps)  # tom de +h*Rb/2
    alto = np.abs(janelas @ giro)
    baixo = np.abs(janelas @ np.conj(giro))
    return np.asarray(alto > baixo, dtype=np.uint8)


def demodular(
    amostras: Sinal,
    config: ConfigModem,
    n_bits: int,
    fase: float = 0.0,
    limiar: float | None = None,
) -> Bits:
    """Bits a partir do sinal recebido, com o instante de amostragem conhecido.

    Args:
        amostras: sinal recebido, alinhado com o início da modulação.
        config: a mesma configuração do modulador.
        n_bits: quantidade de bits a recuperar.
        fase: fase da portadora em radianos (só a BPSK coerente usa).
        limiar: limiar da OOK; se omitido, é ajustado pelos próprios símbolos (k-médias).

    Raises:
        ValueError: n_bits não positivo ou sinal curto demais.
    """
    if n_bits <= 0:
        raise ValueError(f"quantidade de bits inválida: {n_bits}")
    if config.modulacao == "fsk":
        return _demodular_fsk(amostras, config, n_bits)
    if config.modulacao == "dbpsk":
        z = saida_casada(amostras, config, n_bits + 1)
        return (np.real(z[1:] * np.conj(z[:-1])) < 0).astype(np.uint8)
    z = saida_casada(amostras, config, n_bits)
    if config.modulacao == "bpsk":
        return np.asarray(np.real(z * np.exp(-1j * fase)) > 0, dtype=np.uint8)
    modulo = np.abs(z)
    corte = _limiar_dois_niveis(modulo) if limiar is None else limiar
    return np.asarray(modulo > corte, dtype=np.uint8)

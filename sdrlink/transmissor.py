"""Transmissor de prova: payloads do avaliador -> pacotes numerados -> amostras + log do TX.

Requisitos: PKT-04 (payloads de 128 bytes lidos do arquivo do avaliador), TX-01
(log do que foi transmitido, referência da PER), PLT-05 (banda dentro da faixa
autorizada). Achado tratado: A4 (a referência repetia o mesmo quadro em buffer
cíclico, sem log).

O fluxo é entregue em blocos de tamanho fixo, que é o que o Pluto exige no modo
não cíclico (sdrlink.hw.pluto_tx.transmitir_fluxo). Cada quadro é modulado e
deslocado para +deslocamento_hz com a fase contínua entre blocos. Só começam
pacotes dentro da janela pedida (seção 8 do enunciado: contam os pacotes cuja
transmissão começa dentro da janela); o pacote que começou termina.

Formatos aceitos para o arquivo de payloads (o do avaliador ainda não foi divulgado):
    .bin  bytes corridos, `tamanho` bytes por pacote;
    .txt  um payload em hexadecimal por linha (linhas vazias são ignoradas).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from sdrlink import espectro, modem, quadro
from sdrlink.hw.pluto_tx import FUNDO_ESCALA_DAC
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote

TAMANHO_PAYLOAD = 128  # bytes, payload da prova (seção 12)
AMPLITUDE_PADRAO = 0.7 * 2**15  # pico do sinal: 70% do fundo de escala do DAC de 16 bits do Pluto

BLOCO_PADRAO = 2**18  # amostras por bloco entregue ao Pluto (128 ms a 2,048 MS/s)
BITS_REFERENCIA = 4000  # sequência aleatória usada para medir pico e banda do sinal
SEMENTE_REFERENCIA = 20261121
MAX_PACOTES = 10_000_000


@dataclass(frozen=True)
class ConfigTransmissor:
    """Parâmetros do transmissor de prova.

    Attributes:
        modem: modulação e pulso (sps = amostras por bit na taxa do DAC).
        taxa_sps: taxa de amostragem do DAC (a mesma do RX, para sps inteiro dos dois lados).
        deslocamento_hz: posição do sinal em relação ao LO.
        amplitude: pico desejado do sinal, em unidades do DAC.
    """

    modem: ConfigModem
    taxa_sps: float
    deslocamento_hz: float = 250e3
    amplitude: float = AMPLITUDE_PADRAO

    def __post_init__(self) -> None:
        """Rejeita parâmetros incoerentes.

        Raises:
            ValueError: taxa, deslocamento ou amplitude inválidos.
        """
        if self.taxa_sps <= 0:
            raise ValueError(f"taxa de amostragem inválida: {self.taxa_sps}")
        if abs(self.deslocamento_hz) >= self.taxa_sps / 2:
            raise ValueError(f"deslocamento fora da banda do DAC: {self.deslocamento_hz}")
        if not 0 < self.amplitude <= FUNDO_ESCALA_DAC:
            raise ValueError(f"amplitude fora do fundo de escala do DAC: {self.amplitude}")

    @property
    def taxa_bits(self) -> float:
        """Taxa de bits (um bit por símbolo em todas as modulações)."""
        return self.taxa_sps / self.modem.sps

    def _referencia(self) -> NDArray[np.complex128]:
        """Sinal de referência (bits aleatórios fixos) para medir pico e banda."""
        rng = np.random.default_rng(SEMENTE_REFERENCIA)
        return modem.modular(rng.integers(0, 2, BITS_REFERENCIA).astype(np.uint8), self.modem)

    def escala(self) -> float:
        """Fator que leva o pico do sinal modulado à amplitude pedida.

        O pico é medido numa sequência longa de referência, com 10% de folga: o RRC
        passa um pouco do nível dos símbolos, e o fator tem de ser o mesmo em todos
        os quadros (o RX estima o nível pelo preâmbulo de cada quadro, mas a OOK
        precisa de nível estável dentro do quadro).
        """
        return self.amplitude / (1.1 * float(np.max(np.abs(self._referencia()))))

    def banda_99_hz(self) -> tuple[float, float]:
        """Limites da banda a 99% do sinal transmitido, em relação ao LO."""
        baixo, alto = espectro.banda_ocupada(self._referencia(), self.taxa_sps, nperseg=4096)
        return baixo + self.deslocamento_hz, alto + self.deslocamento_hz


@dataclass(frozen=True)
class RegistroTx:
    """Um pacote transmitido: o que entra no log do TX.

    Attributes:
        pacote: sequência e payload.
        amostra_inicio: amostra do fluxo em que o quadro começa (tempo = amostra / taxa).
    """

    pacote: Pacote
    amostra_inicio: int


def ler_payloads(caminho: Path, tamanho: int = TAMANHO_PAYLOAD) -> list[bytes]:
    """Payloads do arquivo do avaliador (.bin corrido ou .txt com hexadecimal por linha).

    Raises:
        ValueError: extensão desconhecida, arquivo vazio ou tamanho de payload errado.
    """
    if caminho.suffix == ".bin":
        dados = caminho.read_bytes()
        if len(dados) == 0 or len(dados) % tamanho:
            raise ValueError(f"{caminho.name}: {len(dados)} bytes não é múltiplo de {tamanho}")
        return [dados[k : k + tamanho] for k in range(0, len(dados), tamanho)]
    if caminho.suffix != ".txt":
        raise ValueError(f"formato de payloads desconhecido: {caminho.suffix} (use .bin ou .txt)")
    linhas = [linha.strip() for linha in caminho.read_text(encoding="utf-8").splitlines()]
    payloads = [bytes.fromhex(linha) for linha in linhas if linha]
    errados = [k for k, p in enumerate(payloads) if len(p) != tamanho]
    if not payloads or errados:
        raise ValueError(
            f"{caminho.name}: payloads vazios ou com tamanho diferente de {tamanho}: {errados[:5]}"
        )
    return payloads


def numerar(payloads: list[bytes], sequencia_inicial: int = 0) -> list[Pacote]:
    """Pacotes numerados em ordem; a sequência volta a 0 depois de 65535."""
    return [
        Pacote((sequencia_inicial + k) % (quadro.SEQUENCIA_MAX + 1), p)
        for k, p in enumerate(payloads[:MAX_PACOTES])
    ]


def fluxo(
    pacotes: list[Pacote],
    config: ConfigTransmissor,
    duracao_s: float,
    tamanho_bloco: int = BLOCO_PADRAO,
) -> Iterator[tuple[NDArray[np.complex64], list[RegistroTx]]]:
    """Blocos de tamanho fixo do sinal transmitido e os pacotes que começaram em cada bloco.

    Os quadros vão um atrás do outro (a guarda de 16 bits do quadro separa um do
    outro). Um pacote só começa se a sua primeira amostra cair antes de duracao_s;
    o último bloco é completado com zeros.

    Raises:
        ValueError: duração ou tamanho de bloco inválidos.
    """
    if duracao_s <= 0 or tamanho_bloco <= 0:
        raise ValueError("duração e tamanho de bloco precisam ser positivos")
    limite = int(duracao_s * config.taxa_sps)
    escala = config.escala()
    giro = 2j * np.pi * config.deslocamento_hz / config.taxa_sps
    acumulado = np.zeros(0, dtype=np.complex128)  # gerado e ainda não entregue
    posicao = 0  # amostras geradas até agora
    pendentes: list[RegistroTx] = []  # pacotes ainda não entregues com um bloco
    for p in pacotes:
        if posicao >= limite:
            break
        onda = modem.modular(quadro.montar_quadro(p), config.modem) * escala
        deslocada = onda * np.exp(giro * np.arange(posicao, posicao + len(onda)))  # fase contínua
        acumulado = np.concatenate([acumulado, deslocada])
        pendentes.append(RegistroTx(p, posicao))
        posicao += len(onda)
        # um bloco só sai logo depois de um quadro entrar, e esse quadro começa antes do fim
        # do primeiro bloco que sai: os pacotes pendentes vão todos com esse bloco
        for _ in range(len(acumulado) // tamanho_bloco):
            yield acumulado[:tamanho_bloco].astype(np.complex64), pendentes
            pendentes = []
            acumulado = acumulado[tamanho_bloco:]
    if len(acumulado) or pendentes:
        final = np.zeros(tamanho_bloco, dtype=np.complex64)
        final[: len(acumulado)] = acumulado
        yield final, pendentes


def gravar_log(registros: list[RegistroTx], caminho: Path) -> Path:
    """Grava o log do TX: uma linha "sequência<TAB>payload em hex" por pacote (formato do RX).

    Raises:
        ValueError: caminho sem a extensão .txt.
    """
    if caminho.suffix != ".txt":
        raise ValueError(f"o log do TX deve ser .txt: {caminho}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = [f"{r.pacote.sequencia}\t{r.pacote.payload.hex()}" for r in registros]
    caminho.write_text("\n".join(linhas) + ("\n" if linhas else ""), encoding="utf-8", newline="\n")
    return caminho

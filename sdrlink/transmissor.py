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

TAMANHO_PAYLOAD = quadro.PAYLOAD_PROVA_BYTES  # 128 bytes, payload da prova (seção 12)
AMPLITUDE_PADRAO = 0.7 * 2**15  # pico do sinal: 70% do fundo de escala do DAC de 16 bits do Pluto

BLOCO_PADRAO = 2**18  # amostras por bloco entregue ao Pluto (128 ms a 2,048 MS/s)
BITS_REFERENCIA = 4000  # sequência aleatória usada para medir pico e banda do sinal
SIMBOLOS_REFERENCIA_MIN = 2000  # e pelo menos tantos símbolos (a 8-PSK leva 3 bits por símbolo)
SEMENTE_REFERENCIA = 20261121
MAX_PACOTES = 10_000_000


@dataclass(frozen=True)
class ConfigTransmissor:
    """Parâmetros do transmissor de prova.

    Attributes:
        modem: modulação e pulso (sps = amostras por símbolo na taxa do DAC).
        taxa_sps: taxa de amostragem do DAC (a mesma do RX, para sps inteiro dos dois lados).
        deslocamento_hz: posição do sinal em relação ao LO.
        amplitude: pico desejado do sinal, em unidades do DAC.
        fec: codifica o corpo de cada quadro (sdrlink.codigo, bloco 09).
        emendar_caudas: nas modulações lineares, o quadro seguinte começa logo depois do
            último símbolo do anterior, com as caudas do pulso somadas (bloco 12).
    """

    modem: ConfigModem
    taxa_sps: float
    deslocamento_hz: float = 250e3
    amplitude: float = AMPLITUDE_PADRAO
    fec: bool = False
    emendar_caudas: bool = False  # ligada pelos perfis da prova A (bloco 12)

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
        """Taxa de bits do corpo (o dobro da de símbolos na DQPSK, o triplo na 8-PSK)."""
        return self.taxa_sps / self.modem.sps * self.modem.bits_por_simbolo

    def _referencia(self) -> NDArray[np.complex128]:
        """Sinal de referência (bits aleatórios fixos) para medir pico e banda."""
        rng = np.random.default_rng(SEMENTE_REFERENCIA)
        n_bits = max(BITS_REFERENCIA, SIMBOLOS_REFERENCIA_MIN * self.modem.bits_por_simbolo)
        return modem.modular(rng.integers(0, 2, n_bits).astype(np.uint8), self.modem)

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
    """Pacotes numerados em ordem; a sequência volta a 0 depois de 2^24 - 1."""
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
    outro). Com config.emendar_caudas, nas modulações lineares, o quadro seguinte
    começa logo depois do último símbolo do anterior e as caudas do pulso se somam
    (bloco 12): o sinal fica igual ao de uma modulação contínua, e os 12 símbolos de
    cauda por quadro deixam de ser tempo morto. Sem a opção, e sempre na 2-FSK (a
    fase é contínua dentro do quadro, e somar as caudas não teria o mesmo efeito), os
    quadros vão encostados, sem sobreposição. Um pacote
    só começa se a sua primeira amostra cair antes de duracao_s; o último bloco é
    completado com zeros.

    Raises:
        ValueError: duração ou tamanho de bloco inválidos.
    """
    if duracao_s <= 0 or tamanho_bloco <= 0:
        raise ValueError("duração e tamanho de bloco precisam ser positivos")
    limite = int(duracao_s * config.taxa_sps)
    escala = config.escala()
    giro = 2j * np.pi * config.deslocamento_hz / config.taxa_sps
    sobrepoe = config.modem.linear and config.emendar_caudas
    cauda = len(config.modem.formato()) - 1 if sobrepoe else 0
    acumulado = np.zeros(0, dtype=np.complex128)  # amostras a partir de `entregue`
    entregue = 0  # amostras já entregues em blocos
    posicao = 0  # onde começa o próximo quadro
    pendentes: list[RegistroTx] = []  # pacotes ainda não entregues com um bloco
    for p in pacotes:
        if posicao >= limite:
            break
        bits = quadro.montar_quadro(p, config.fec)
        onda = modem.modular(bits, config.modem, quadro.BITS_PREFIXO) * escala
        deslocada = onda * np.exp(giro * np.arange(posicao, posicao + len(onda)))  # fase contínua
        fim = posicao + len(onda) - entregue
        if fim > len(acumulado):
            acumulado = np.concatenate([acumulado, np.zeros(fim - len(acumulado), complex)])
        acumulado[posicao - entregue : fim] += deslocada  # a cauda do anterior se soma aqui
        pendentes.append(RegistroTx(p, posicao))
        posicao += len(onda) - cauda
        # só as amostras antes do próximo quadro estão prontas (ele ainda soma a cauda
        # desta). Um bloco só sai logo depois de um quadro entrar, e esse quadro começa
        # antes do fim do primeiro bloco que sai: os pacotes pendentes vão com esse bloco
        for _ in range((posicao - entregue) // tamanho_bloco):
            yield acumulado[:tamanho_bloco].astype(np.complex64), pendentes
            pendentes = []
            acumulado = acumulado[tamanho_bloco:]
            entregue += tamanho_bloco
    while len(acumulado) > tamanho_bloco:  # o resto, com a cauda do último quadro
        yield acumulado[:tamanho_bloco].astype(np.complex64), pendentes
        pendentes = []
        acumulado = acumulado[tamanho_bloco:]
    if len(acumulado) or pendentes:
        final = np.zeros(tamanho_bloco, dtype=np.complex64)
        final[: len(acumulado)] = acumulado
        yield final, pendentes


def pacotes_que_cabem(config: ConfigTransmissor, duracao_s: float) -> int:
    """Quantos pacotes de 128 bytes começam dentro da janela (o que o fluxo mandaria).

    Se o arquivo do avaliador tiver menos payloads que isso, o TX fica sem payloads antes
    do fim da janela e o goodput cai: na prova de 60 s simulada com DQPSK, 60 000 payloads
    acabaram aos 51 s (bloco 10).

    Raises:
        ValueError: duração não positiva.
    """
    if duracao_s <= 0:
        raise ValueError(f"duração inválida: {duracao_s}")
    periodo = amostras_por_quadro(
        config.modem, fec=config.fec, emendar_caudas=config.emendar_caudas
    )
    return -(-int(duracao_s * config.taxa_sps) // periodo)


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


def amostras_por_quadro(
    config: ConfigModem,
    tamanho_payload: int = TAMANHO_PAYLOAD,
    fec: bool = False,
    emendar_caudas: bool = False,
) -> int:
    """Período entre quadros consecutivos no fluxo do TX, em amostras.

    Sem emenda, é a forma de onda inteira de um quadro: os símbolos, o de referência
    da modulação diferencial e os 12 da cauda do pulso, vezes sps. Com emendar_caudas
    (só nas modulações lineares) a cauda se sobrepõe ao quadro seguinte e o período
    perde os 12 símbolos de cauda.
    """
    vazio = quadro.montar_quadro(Pacote(0, bytes(tamanho_payload)), fec)
    onda = modem.modular(vazio, config, quadro.BITS_PREFIXO)
    return len(onda) - (len(config.formato()) - 1 if config.linear and emendar_caudas else 0)

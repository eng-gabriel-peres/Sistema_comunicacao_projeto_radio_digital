"""O dia da prova: arquivo qualquer em pacotes, arquivo remontado, resumo do RX e alcance.

Requisitos: seção 8 do enunciado (provas A e B) e o anúncio do professor de que ele vai
entregar um arquivo criptografado para transmitir (25/11/2026). Feito no bloco 26.

- fatiar(): qualquer arquivo vira payloads de 128 bytes; o último é completado com zeros.
- remontar(): os payloads recebidos, na ordem da sequência, voltam a formar o arquivo;
  os que faltam ficam com zeros e são listados.
- resumo_da_recepcao(): o que o RX sabe sozinho, sem o log do TX: pacotes únicos, buracos
  de sequência (perdas estimadas), goodput estimado na janela e o ritmo no tempo.
- alcance(): os resumos de cada posição da prova B numa tabela por distância, com o
  critério da prova (goodput de 10 kbit/s, PER de 1% e 500 pacotes).
- ocupacao_dos_canais(): quanto cada deslocamento candidato sofre com surtos de
  interferência, numa gravação sem o TX (a faixa de 915 MHz tem aparelhos ISM que
  transmitem em surtos, achados na bancada de 25/11).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from sdrlink.quadro import Pacote
from sdrlink.transmissor import TAMANHO_PAYLOAD, ler_payloads

GOODPUT_MIN_BPS = 10e3  # prova B, seção 8 do enunciado
PER_MAX = 0.01
PACOTES_MIN_B = 500
BANDA_MAX_KHZ = 1000.0  # prova A: banda a 99% de até 1 MHz (CMP-A)
SEGUNDO = 1.0
PERCENTIL_SURTO = 99.0  # o surto é o que aparece em 1% do tempo acima do típico
MAX_POSICOES = 1000
JANELAS_MIN = 10  # janelas de FFT para um percentil fazer sentido


def fatiar(dados: bytes, tamanho: int = TAMANHO_PAYLOAD) -> list[bytes]:
    """O arquivo em payloads de `tamanho` bytes; o último é completado com zeros.

    Raises:
        ValueError: arquivo vazio.
    """
    if not dados:
        raise ValueError("arquivo vazio")
    falta = (-len(dados)) % tamanho
    corpo = dados + bytes(falta)
    return [corpo[k : k + tamanho] for k in range(0, len(corpo), tamanho)]


def ler_arquivo(caminho: Path) -> tuple[list[bytes], str | None]:
    """Os payloads de qualquer arquivo e um aviso, se houver.

    `.txt` é o formato do enunciado (um payload em hexadecimal por linha) e continua
    estrito. Qualquer outra extensão (o arquivo criptografado do professor, um `.bin`) é
    lida como bytes e fatiada em payloads de 128 bytes; se o tamanho não for múltiplo de
    128, o último payload é completado com zeros e o aviso diz quantos.

    Raises:
        ValueError: arquivo vazio ou `.txt` fora do formato.
    """
    if caminho.suffix == ".txt":
        return ler_payloads(caminho), None
    dados = caminho.read_bytes()
    payloads = fatiar(dados)
    falta = len(payloads) * TAMANHO_PAYLOAD - len(dados)
    aviso = None
    if falta:
        aviso = (
            f"{caminho.name}: {len(dados)} bytes não é múltiplo de {TAMANHO_PAYLOAD}; "
            f"o último dos {len(payloads)} payloads leva {falta} bytes zero no fim"
        )
    return payloads, aviso


def repetir_ate(payloads: list[bytes], quantidade: int) -> list[bytes]:
    """Os payloads repetidos em ciclo até `quantidade` (para encher a janela da prova).

    Raises:
        ValueError: lista vazia ou quantidade não positiva.
    """
    if not payloads or quantidade <= 0:
        raise ValueError("nada para repetir")
    voltas = -(-quantidade // len(payloads))
    return (payloads * voltas)[:quantidade]


def so_os_da_prova(pacotes: list[Pacote]) -> tuple[list[Pacote], int]:
    """Os pacotes de 128 bytes e quantos de outro tamanho foram descartados.

    No ensaio com dois PCs (25/11) um sinal fraco gerou falsos positivos que passaram no
    CRC-16 com 80 e 208 bytes de payload, e o remontar recusava a lista inteira. Na prova
    todo payload tem 128 bytes; um tamanho diferente só pode ser um quadro falso.
    """
    validos = [p for p in pacotes if len(p.payload) == TAMANHO_PAYLOAD]
    return validos, len(pacotes) - len(validos)


def remontar(pacotes: list[Pacote], n_pacotes: int | None = None) -> tuple[bytes, list[int]]:
    """O arquivo a partir dos pacotes recebidos, na ordem da sequência, e as sequências que faltam.

    `n_pacotes` é quantos pacotes o arquivo tem (se o RX souber); senão, vai até a maior
    sequência recebida. Os que faltam viram zeros do tamanho de um payload.

    Raises:
        ValueError: nenhum pacote, ou payloads de tamanhos diferentes.
    """
    if not pacotes:
        raise ValueError("nenhum pacote recebido")
    tamanhos = {len(p.payload) for p in pacotes}
    if len(tamanhos) != 1:
        raise ValueError(f"payloads de tamanhos diferentes: {sorted(tamanhos)}")
    tamanho = tamanhos.pop()
    por_sequencia = {p.sequencia: p.payload for p in pacotes}
    total = n_pacotes if n_pacotes is not None else max(por_sequencia) + 1
    faltando = [k for k in range(total) if k not in por_sequencia]
    dados = b"".join(por_sequencia.get(k, bytes(tamanho)) for k in range(total))
    return dados, faltando


@dataclass(frozen=True)
class ResumoRx:
    """O que o RX sabe sem o log do TX.

    Attributes:
        unicos: pacotes aceitos sem repetição.
        primeira, ultima: menor e maior sequência recebidas.
        buracos: sequências entre a primeira e a última que não chegaram.
        per_estimada: buracos / (ultima - primeira + 1); não conta perdas no começo e no fim.
        goodput_bps: bits úteis dos pacotes únicos divididos pela janela.
        por_segundo: pacotes aceitos em cada segundo depois do primeiro.
    """

    unicos: int
    primeira: int
    ultima: int
    buracos: int
    per_estimada: float
    goodput_bps: float
    por_segundo: list[int]


def resumo_da_recepcao(
    pacotes: list[Pacote], instantes_s: list[float], janela_s: float
) -> ResumoRx:
    """Resumo da recepção a partir dos pacotes aceitos e do instante de cada um na captura.

    Raises:
        ValueError: nenhum pacote, listas de tamanhos diferentes ou janela inválida.
    """
    if not pacotes or len(pacotes) != len(instantes_s):
        raise ValueError("pacotes e instantes vazios ou de tamanhos diferentes")
    if janela_s <= 0:
        raise ValueError(f"janela inválida: {janela_s}")
    vistos: dict[int, Pacote] = {}
    for p in pacotes:
        vistos.setdefault(p.sequencia, p)
    sequencias = sorted(vistos)
    primeira, ultima = sequencias[0], sequencias[-1]
    esperados = ultima - primeira + 1
    buracos = esperados - len(sequencias)
    bits = sum(8 * len(p.payload) for p in vistos.values())
    t0 = min(instantes_s)
    segundos = np.floor((np.asarray(instantes_s) - t0) / SEGUNDO).astype(int)
    por_segundo = np.bincount(segundos).tolist()
    return ResumoRx(
        unicos=len(sequencias),
        primeira=primeira,
        ultima=ultima,
        buracos=buracos,
        per_estimada=buracos / esperados,
        goodput_bps=bits / janela_s,
        por_segundo=[int(v) for v in por_segundo],
    )


@dataclass(frozen=True)
class Posicao:
    """Uma posição da prova B: distância e o que o RX mediu ali."""

    distancia_m: float
    goodput_bps: float
    per: float
    pacotes: int
    ebn0_db: float | None

    @property
    def passou(self) -> bool:
        """Critério da prova B: goodput, PER e número mínimo de pacotes."""
        return (
            self.goodput_bps >= GOODPUT_MIN_BPS
            and self.per <= PER_MAX
            and self.pacotes >= PACOTES_MIN_B
        )


def criterio_prova_a(per: float | None, banda_khz: float | None) -> str:
    """Diz se o ensaio da prova A vale: PER de até 1% e banda a 99% abaixo de 1 MHz (CMP-A).

    Na bancada de 25/11 a 8-PSK deu 1 690 kbit/s com PER de 5%: mais goodput que a
    DQPSK, mas fora da regra. Sem a banda medida (sinal fraco) o critério da banda fica
    em aberto.
    """
    if per is None:
        situacao = "NÃO PASSA: sem PER"
    elif per > PER_MAX:
        situacao = f"NÃO PASSA: PER de {100 * per:.2f}% acima de {100 * PER_MAX:g}%"
    elif banda_khz is None:
        situacao = "PASSA na PER; banda não medida"
    elif banda_khz >= BANDA_MAX_KHZ:
        situacao = f"NÃO PASSA: banda de {banda_khz:g} kHz"
    else:
        situacao = "PASSA (PER de até 1% e banda abaixo de 1 MHz)"
    return situacao


def alcance(posicoes: list[Posicao]) -> tuple[list[Posicao], float | None]:
    """As posições em ordem de distância e a maior distância validada (None se nenhuma)."""
    ordenadas = sorted(posicoes[:MAX_POSICOES], key=lambda p: p.distancia_m)
    validas = [p.distancia_m for p in ordenadas if p.passou]
    return ordenadas, (max(validas) if validas else None)


def ocupacao_dos_canais(
    amostras: NDArray[np.complexfloating],
    taxa_sps: float,
    candidatos_hz: list[float],
    meia_largura_hz: float,
    n_fft: int = 8192,
) -> dict[float, float]:
    """Para cada deslocamento candidato, o pior surto na faixa dele (dB acima do típico).

    O espectro é calculado em janelas de n_fft amostras; o surto de cada frequência é o
    percentil PERCENTIL_SURTO da potência dividido pela mediana. Um canal limpo fica perto
    do que o próprio ruído dá (cerca de 9 dB com 8192 pontos).

    Raises:
        ValueError: gravação curta demais ou nenhum candidato.
    """
    m = len(amostras) // n_fft
    if m < JANELAS_MIN or not candidatos_hz:
        raise ValueError("gravação curta demais ou nenhum candidato")
    janelas = np.asarray(amostras[: m * n_fft]).reshape(m, n_fft) * np.hanning(n_fft)
    potencia = np.abs(np.fft.fftshift(np.fft.fft(janelas, axis=1), axes=1)) ** 2
    frequencias = np.fft.fftshift(np.fft.fftfreq(n_fft, 1 / taxa_sps))
    surto = 10 * np.log10(
        np.percentile(potencia, PERCENTIL_SURTO, axis=0) / np.median(potencia, axis=0)
    )
    resultado = {}
    for c in candidatos_hz:
        faixa = np.abs(frequencias - c) <= meia_largura_hz
        if not np.any(faixa):
            raise ValueError(f"candidato fora da faixa gravada: {c} Hz")
        resultado[c] = float(surto[faixa].max())
    return resultado

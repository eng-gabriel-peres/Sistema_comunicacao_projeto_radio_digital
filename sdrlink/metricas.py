"""PER e goodput a partir do log do TX e da saída do RX (seção 7 do enunciado).

Requisitos: MET-01 (goodput), MET-02 (PER). É a mesma conta que o avaliador faz
na prova: compara o arquivo de saída do receptor com o log do transmissor.

Definições (seção 7):
    goodput = bits úteis de payload entregues corretamente / duração total do ensaio;
              excluem-se cabeçalho, sequência, CRC, guarda e dados duplicados;
    PER     = pacotes não recebidos corretamente / pacotes transmitidos (log do TX);
              perdidos, com CRC inválido ou com conteúdo diferente contam como falha.

Os dois arquivos têm o mesmo formato: uma linha "sequência<TAB>payload em hex".

BER (MET-03, seção 7: "bits de payload incorretos / bits de payload comparados com
uma referência conhecida; a política de contabilização de quadros perdidos deve
ser apresentada separadamente"): no ensaio de BER, o payload do pacote de
sequência k é payload_conhecido(k), uma sequência pseudoaleatória fixa. O RX
compara os bits de payload de todo quadro detectado, inclusive os de CRC falho.
Quando o CRC falha, a sequência pode estar corrompida, e ela é deduzida assim:

1. As detecções são encadeadas em segmentos: cada uma entra no segmento cujo
   último quadro está um número inteiro de períodos antes dela (o TX manda um
   quadro atrás do outro), com uma tolerância de uns 2 bits. A referência anda
   quadro a quadro, então a diferença de relógio entre Pluto e RTL (alguns ppm,
   centenas de amostras em 60 s) não acumula. Uma detecção que não encaixa em
   nenhum segmento abre outro; segmento com uma detecção só é falso alarme.
2. Em cada segmento, o campo de sequência decodificado menos a posição do quadro
   no segmento tem de dar o mesmo número: o valor mais votado vence (com pelo
   menos 2 votos). Não depende de nenhum quadro ter CRC válido, o que importa
   justamente na relação sinal-ruído baixa, onde a BER interessa.

Os quadros não detectados ficam fora da BER e são contados à parte (PER).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from sdrlink import quadro
from sdrlink.quadro import Pacote

SEMENTE_BER = 20261122  # semente da sequência pseudoaleatória conhecida do ensaio de BER
SEGMENTOS_ABERTOS = 8  # segmentos recentes em que uma detecção pode entrar
VOTOS_MIN = 2  # quadros que precisam concordar na sequência do segmento


def ler_pacotes(caminho: Path) -> list[Pacote]:
    """Lê um log do TX ou uma saída do RX ("sequência<TAB>payload em hex" por linha).

    Raises:
        ValueError: linha fora do formato.
    """
    pacotes = []
    for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        campos = linha.split("\t")
        if len(campos) != 2:  # noqa: PLR2004 (sequência e payload)
            raise ValueError(f"{caminho.name}, linha {n}: esperado 'sequência<TAB>payload'")
        pacotes.append(Pacote(int(campos[0]), bytes.fromhex(campos[1])))
    return pacotes


def avaliar(
    transmitidos: list[Pacote], recebidos: list[Pacote], duracao_s: float
) -> dict[str, float]:
    """PER, goodput e a classificação de cada pacote recebido.

    Um recebido é "certo" quando a sequência e o payload são iguais aos de um
    transmitido; cada transmitido conta no máximo uma vez.

    Raises:
        ValueError: duração não positiva ou log do TX vazio.
    """
    if duracao_s <= 0:
        raise ValueError(f"duração inválida: {duracao_s}")
    if not transmitidos:
        raise ValueError("log do TX vazio: não há como calcular a PER")
    por_sequencia = {p.sequencia: p.payload for p in transmitidos}
    certos: set[tuple[int, bytes]] = set()
    errados = espurios = duplicados = 0
    for p in recebidos:
        chave = (p.sequencia, p.payload)
        if chave in certos:
            duplicados += 1
        elif por_sequencia.get(p.sequencia) == p.payload:
            certos.add(chave)
        elif p.sequencia in por_sequencia:
            errados += 1  # sequência existe, conteúdo diferente: falha
        else:
            espurios += 1  # sequência que o TX não mandou
    bits_uteis = sum(8 * len(payload) for _, payload in certos)
    return {
        "transmitidos": len(transmitidos),
        "recebidos_certos": len(certos),
        "conteudo_diferente": errados,
        "espurios": espurios,
        "duplicados": duplicados,
        "perdidos": len(transmitidos) - len(certos),
        "per": (len(transmitidos) - len(certos)) / len(transmitidos),
        "goodput_bps": bits_uteis / duracao_s,
        "duracao_s": duracao_s,
    }


def payload_conhecido(sequencia: int, tamanho: int = quadro.PAYLOAD_PROVA_BYTES) -> bytes:
    """Payload pseudoaleatório fixo do pacote de número `sequencia` (ensaio de BER)."""
    gerador = np.random.default_rng([SEMENTE_BER, sequencia % (quadro.SEQUENCIA_MAX + 1)])
    return gerador.integers(0, 256, tamanho, dtype=np.uint8).tobytes()


class ComBits(Protocol):
    """O que medir_ber usa de cada detecção (sdrlink.receptor.Deteccao)."""

    @property
    def inicio(self) -> float:
        """Amostra em que o quadro começa."""

    @property
    def pacote(self) -> Pacote | None:
        """Pacote, quando o CRC confere."""

    @property
    def bits(self) -> NDArray[np.uint8] | None:
        """Bits demodulados depois do sync."""


Bits = NDArray[np.uint8]
Segmento = list[tuple[ComBits, Bits, int]]  # (detecção, bits, posição do quadro no segmento)


def _segmentos(
    deteccoes: list[tuple[ComBits, Bits]], periodo: float, tolerancia: float
) -> list[Segmento]:
    """Encadeia as detecções em segmentos de quadros a um número inteiro de períodos.

    Cada detecção é testada contra o último quadro dos SEGMENTOS_ABERTOS segmentos mais
    recentes, do mais novo para o mais antigo; se não encaixa em nenhum, abre outro.
    """
    segmentos: list[Segmento] = []
    for d, bits in sorted(deteccoes, key=lambda par: par[0].inicio):
        destino: tuple[Segmento, int] | None = None
        for seg in reversed(segmentos[-SEGMENTOS_ABERTOS:]):
            ultimo, _, posicao = seg[-1]
            passos = round((d.inicio - ultimo.inicio) / periodo)
            if passos >= 1 and abs(d.inicio - ultimo.inicio - passos * periodo) <= tolerancia:
                destino = (seg, posicao + passos)
                break
        if destino is None:
            segmentos.append([(d, bits, 0)])
        else:
            destino[0].append((d, bits, destino[1]))
    return segmentos


def _sequencia_base(segmento: Segmento) -> int | None:
    """Sequência do primeiro quadro do segmento, por votação (pelo menos VOTOS_MIN votos)."""
    modulo = quadro.SEQUENCIA_MAX + 1
    campo = slice(quadro.BITS_COMPRIMENTO, quadro.BITS_CABECALHO)
    votos = []
    for _, bits, posicao in segmento:
        lida = int.from_bytes(quadro.bits_para_bytes(bits[campo]), "big")
        votos.append((lida - posicao) % modulo)
    valores, contagens = np.unique(votos, return_counts=True)
    melhor = int(np.argmax(contagens))
    return int(valores[melhor]) if contagens[melhor] >= VOTOS_MIN else None


def medir_ber(
    deteccoes: Sequence[ComBits],
    periodo_amostras: float,
    tolerancia_amostras: float,
    tamanho: int = 128,
) -> dict[str, float]:
    """BER de payload com sequência conhecida, em todos os quadros detectados e identificados.

    Args:
        deteccoes: detecções do receptor com os bits guardados (guardar_bits=True).
        periodo_amostras: duração de um quadro na captura (transmissor.amostras_por_quadro).
        tolerancia_amostras: quanto o início pode fugir da posição esperada (uns 2 bits).
        tamanho: bytes de payload de cada pacote.

    Raises:
        ValueError: período ou tolerância inválidos.
    """
    if periodo_amostras <= 0 or not 0 < tolerancia_amostras < periodo_amostras / 2:
        raise ValueError("período ou tolerância inválidos")
    inicio_payload = quadro.BITS_CABECALHO
    com_bits = [
        (d, d.bits)
        for d in deteccoes
        if d.bits is not None and len(d.bits) >= inicio_payload + 8 * tamanho
    ]
    erros = comparados = crc_falho = fora = usados = 0
    for segmento in _segmentos(com_bits, periodo_amostras, tolerancia_amostras):
        base = _sequencia_base(segmento) if len(segmento) >= VOTOS_MIN else None
        if base is None:
            fora += len(segmento)  # falso alarme ou segmento sem sequência confiável
            continue
        usados += 1
        for d, bits, posicao in segmento:
            seq = (base + posicao) % (quadro.SEQUENCIA_MAX + 1)
            esperado = np.unpackbits(np.frombuffer(payload_conhecido(seq, tamanho), np.uint8))
            erros += int(np.sum(bits[inicio_payload : inicio_payload + 8 * tamanho] != esperado))
            comparados += 8 * tamanho
            crc_falho += d.pacote is None
    return {
        "quadros_comparados": comparados // (8 * tamanho),
        "quadros_com_crc_falho_comparados": crc_falho,
        "deteccoes_fora_de_posicao": fora,
        "segmentos": usados,
        "bits_comparados": comparados,
        "bits_errados": erros,
        "ber": erros / comparados if comparados else float("nan"),
    }

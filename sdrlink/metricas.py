"""PER e goodput a partir do log do TX e da saída do RX (seção 7 do enunciado).

Requisitos: MET-01 (goodput), MET-02 (PER). É a mesma conta que o avaliador faz
na prova: compara o arquivo de saída do receptor com o log do transmissor.

Definições (seção 7):
    goodput = bits úteis de payload entregues corretamente / duração total do ensaio;
              excluem-se cabeçalho, sequência, CRC, guarda e dados duplicados;
    PER     = pacotes não recebidos corretamente / pacotes transmitidos (log do TX);
              perdidos, com CRC inválido ou com conteúdo diferente contam como falha.

Os dois arquivos têm o mesmo formato: uma linha "sequência<TAB>payload em hex".
"""

from __future__ import annotations

from pathlib import Path

from sdrlink.quadro import Pacote


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

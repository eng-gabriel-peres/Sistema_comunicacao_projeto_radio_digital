"""Gera as cópias de ensaio da Etapa 2 a partir de referencia/Tx_Rx_OOK/.

As cópias mudam o mínimo necessário para o ensaio e o diff completo fica em
ensaios/etapa2/diferencas.diff, para auditoria. Os originais em referencia/
não são alterados.

Uso: python ensaios/etapa2/gerar_copias.py
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REF = RAIZ / "referencia" / "Tx_Rx_OOK"
DESTINO = RAIZ / "ensaios" / "etapa2"
CORRECAO_PPM = 84  # configs/rtl.toml (calibração de 04/11/2026)

TROCAS_TX = [
    (
        "try:\n    while True:\n        time.sleep(1)\nexcept KeyboardInterrupt:\n"
        r'    print("\nStopping transmission...")'
        "\n    sdr.tx_destroy_buffer()",
        "DURACAO_S = 60  # [ensaio] duração fixa no lugar do while True\ntry:\n"
        "    time.sleep(DURACAO_S)\nfinally:\n"
        r'    print("\nStopping transmission...")'
        "\n    sdr.tx_destroy_buffer()",
    ),
]

TROCAS_RX = [
    (
        "GAIN = 30",
        "GAIN = 10  # [ensaio] com 30 dB o ADC saturou em 29% das amostras (rádios lado a lado)",
    ),
    (
        "FREQ_CORRECTION_PPM = 34",
        f"FREQ_CORRECTION_PPM = {CORRECAO_PPM}  # [ensaio] calibração de 04/11 (configs/rtl.toml)",
    ),
    (
        "samples = capture_chunks(sdr, CAPTURE_SECONDS, CHUNK_SIZE, SAMPLE_RATE)\n",
        "samples = capture_chunks(sdr, CAPTURE_SECONDS, CHUNK_SIZE, SAMPLE_RATE)\n"
        "import time as _t, pathlib as _p  # [ensaio] grava a captura como evidência\n"
        "_BASE = _p.Path(__file__).resolve().parents[2] / 'dados' / 'capturas' / "
        "('ook_ref_' + _t.strftime('%Y%m%d_%H%M%S'))\n"
        "_BASE.parent.mkdir(parents=True, exist_ok=True)\n"
        "np.save(str(_BASE) + '.npy', samples.astype(np.complex64))\n"
        "print(f'[ensaio] captura salva em {_BASE}.npy')\n",
    ),
    (
        "plt.tight_layout()\nplt.show()",
        "plt.tight_layout()\nplt.savefig(str(_BASE) + '.png', dpi=110)  # [ensaio]\n"
        "print(f'[ensaio] figura salva em {_BASE}.png')\nplt.show()",
    ),
]

CABECALHO = (
    "# CÓPIA DE ENSAIO (Etapa 2) de referencia/Tx_Rx_OOK/{origem}.\n"
    "# Gerada por ensaios/etapa2/gerar_copias.py; diferenças em ensaios/etapa2/diferencas.diff\n"
)


def _ler(arquivo: Path) -> str:
    """Lê o original normalizando o fim de linha."""
    return arquivo.read_text(encoding="utf-8").replace("\r\n", "\n")


def gerar(origem: str, destino: str, trocas: list[tuple[str, str]]) -> str:
    """Grava a cópia com as trocas e devolve o diff em relação ao original.

    Raises:
        ValueError: se algum trecho a trocar não aparecer exatamente uma vez.
    """
    original = _ler(REF / origem)
    texto = original
    for velho, novo in trocas:
        if texto.count(velho) != 1:
            raise ValueError(f"{origem}: trecho não encontrado uma única vez: {velho[:40]!r}")
        texto = texto.replace(velho, novo)
    texto = CABECALHO.format(origem=origem) + texto
    (DESTINO / destino).write_text(texto, encoding="utf-8", newline="\n")
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            texto.splitlines(keepends=True),
            f"referencia/Tx_Rx_OOK/{origem}",
            f"ensaios/etapa2/{destino}",
        )
    )


def main() -> int:
    """Gera as duas cópias e o arquivo de diferenças."""
    diff = gerar("pluto_tx_ook_v2.py", "pluto_tx_ook_v2_ensaio.py", TROCAS_TX)
    diff += gerar("rtl_rx_ook_v2.py", "rtl_rx_ook_v2_ensaio.py", TROCAS_RX)
    (DESTINO / "diferencas.diff").write_text(diff, encoding="utf-8", newline="\n")
    print(diff)
    return 0


if __name__ == "__main__":
    sys.exit(main())

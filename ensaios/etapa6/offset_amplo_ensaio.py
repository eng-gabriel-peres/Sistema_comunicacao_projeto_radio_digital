"""Busca de offset ampla na prova B: gravações reais com um offset somado, fixo ou andando.

No ensaio externo de 26/11 a prova B perdeu 34 de 694 pacotes com Eb/N0 de 23,8 dB: o
offset residual mediano foi de 2 080 Hz (180 Hz nos ensaios de 25/11 com o RTL quente),
e o receptor só procurava até 3 000 Hz. Com o RTL frio a frequência anda enquanto ele
esquenta, então os quadros fora da grade se perdiam.

O ensaio pega duas gravações reais da prova B de 25/11 (sinal forte, P1 a −40 dB, e
fraco, −52 dB), soma um offset (fixo de 0 a 9 kHz, ou uma rampa de 1 a 9 kHz ao longo
da gravação, como um RTL esquentando) e decodifica com a busca de 3 kHz e de 10 kHz.
Mede também as detecções e os pacotes falsos com 10 kHz numa gravação só de ruído.

Uso: python ensaios/etapa6/offset_amplo_ensaio.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import config, receptor
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
GRAVACOES = {
    "forte (-40 dB)": RAIZ / "dados/prova/ensaio_20261125/prova_b_P1_20261125_155115.npy",
    "fraco (-52 dB)": RAIZ / "dados/capturas/sessao_20261125_casa/casa_prova_b375_g52_20261125_152101.npy",
}
RUIDO = RAIZ / "dados/capturas/sessao_20261125_casa/ambiente_casa_20261125_151920.npy"
TRECHO_S = 20.0
OFFSETS_FIXOS_HZ = (0.0, 2500.0, 4000.0, 6000.0, 9000.0)
RAMPA_HZ = (1000.0, 9000.0)
BUSCAS_HZ = (3000.0, 10000.0)


def _girar(x: np.ndarray, inicio_hz: float, fim_hz: float, fs: float) -> np.ndarray:
    """Offset que vai de inicio_hz a fim_hz ao longo do trecho (fase contínua)."""
    f = np.linspace(inicio_hz, fim_hz, len(x))
    fase = 2 * np.pi * np.cumsum(f) / fs
    return (x * np.exp(1j * fase)).astype(np.complex64)


def _receber(x: np.ndarray, busca_hz: float) -> tuple[int, int, float]:
    p = config.perfil("prova-b")
    cfg = ConfigReceptor(p.modem(), p.taxa_sps, p.deslocamento_hz, p.limiar, busca_hz, fec=p.fec)
    t0 = time.time()
    deteccoes = receptor.receber(x, cfg)
    aceitos = len({q.sequencia for q in receptor.pacotes_aceitos(deteccoes)})
    return len(deteccoes), aceitos, time.time() - t0


def main() -> int:
    """Roda os casos e grava o registro em dados/logs/."""
    fs = config.perfil("prova-b").taxa_sps
    linhas = []
    for nome, caminho in GRAVACOES.items():
        x = np.asarray(np.load(caminho, mmap_mode="r")[: int(TRECHO_S * fs)])
        casos = [(f"fixo {f:g} Hz", f, f) for f in OFFSETS_FIXOS_HZ]
        casos.append((f"rampa {RAMPA_HZ[0]:g} a {RAMPA_HZ[1]:g} Hz", *RAMPA_HZ))
        for rotulo, a, b in casos:
            y = _girar(x, a, b, fs)
            for busca in BUSCAS_HZ:
                det, aceitos, seg = _receber(y, busca)
                linha = {"gravacao": nome, "caso": rotulo, "busca_hz": busca,
                         "deteccoes": det, "aceitos": aceitos, "tempo_s": round(seg, 1)}  # fmt: skip
                print(linha, flush=True)
                linhas.append(linha)
    ruido = np.asarray(np.load(RUIDO, mmap_mode="r"))
    for busca in BUSCAS_HZ:
        det, aceitos, seg = _receber(ruido, busca)
        linha = {"gravacao": f"só ruído ({len(ruido) / fs:.1f} s)", "caso": "sem TX",
                 "busca_hz": busca, "deteccoes": det, "aceitos": aceitos, "tempo_s": round(seg, 1)}  # fmt: skip
        print(linha, flush=True)
        linhas.append(linha)
    saida = RAIZ / "dados" / "logs" / f"offset_amplo_{carimbo_de_tempo()}.json"
    saida.write_text(
        json.dumps({"versao_do_codigo": versao_do_codigo(), "trecho_s": TRECHO_S, "linhas": linhas},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )  # fmt: skip
    print(f"Registro: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

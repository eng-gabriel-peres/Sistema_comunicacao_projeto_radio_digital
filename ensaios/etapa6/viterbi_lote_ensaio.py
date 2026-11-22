"""Receptor com Viterbi em lote (bloco 11) contra o da tag bloco-10 (um quadro por vez).

Mesmas capturas nas duas versões; compara detecções, instantes, situação, pacotes e os
bits guardados, e mede o tempo. A versão anterior é lida do git
(`git show bloco-10:sdrlink/receptor.py`) e roda com os demais módulos atuais.

Casos (todos com FEC):
    DQPSK 1365 kbit/s no ar (perfil prova-a-fec), 600 quadros a 4 e 6 dB por bit no ar
    DBPSK 25,6 kbit/s no ar (perfil prova-b), 80 quadros a 4 dB
    DBPSK e DQPSK com payloads de 40, 128 e 200 bytes (releitura) e um quadro curto no fim

Uso: python ensaios/etapa6/viterbi_lote_ensaio.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from sdrlink import canal, metricas, modem, quadro, receptor, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
TAG_REFERENCIA = "bloco-10"
FS = 2.048e6


def carregar_referencia():
    """Módulo receptor da tag de referência."""
    fonte = subprocess.run(
        ["git", "show", f"{TAG_REFERENCIA}:sdrlink/receptor.py"],
        cwd=RAIZ, capture_output=True, check=True, text=True, encoding="utf-8",
    ).stdout
    arquivo = Path(tempfile.mkdtemp()) / "receptor_referencia.py"
    arquivo.write_text(fonte, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("receptor_referencia", arquivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["receptor_referencia"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def fluxo(cm, n, ebn0_ar, semente, desl):
    """Quadros um atrás do outro (TX do projeto, com FEC), offset de −1,4 kHz e ruído."""
    rng = np.random.default_rng(semente)
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(n)])
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, desl, fec=True), 1e3)])
    s = s[: np.flatnonzero(s)[-1] + 1].astype(complex)
    x = canal.girar(np.concatenate([np.zeros(50_000), s, np.zeros(20_000)]), -1400.0, FS)
    n0 = np.mean(np.abs(s) ** 2) * cm.sps / cm.bits_por_simbolo / 10 ** (ebn0_ar / 10)
    return x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))


def tamanhos_variados(cm, semente):
    """Quadros de 40, 128 e 200 bytes separados por silêncio e um de 60 bytes no fim da captura."""
    rng = np.random.default_rng(semente)
    partes = [np.zeros(3000, complex)]
    for k, n in enumerate([128, 40, 200, 128, 200, 40, 128]):
        bits = quadro.montar_quadro(Pacote(k, rng.integers(0, 256, n, dtype=np.uint8).tobytes()), fec=True)
        partes += [modem.modular(bits, cm, quadro.BITS_PREFIXO), np.zeros(int(rng.integers(200, 2000)), complex)]
    bits = quadro.montar_quadro(Pacote(99, bytes(range(60))), fec=True)
    partes += [modem.modular(bits, cm, quadro.BITS_PREFIXO), np.zeros(300, complex)]
    amostras_por_bit = cm.sps / cm.bits_por_simbolo  # 6 dB por bit também na DQPSK
    return canal.awgn(canal.girar(np.concatenate(partes), 250e3 - 1500.0, FS), 6.0, amostras_por_bit, rng)


DQPSK = ConfigModem("dqpsk", "rrc", 3, beta=0.25)
CASOS = [
    ("DQPSK 1365 kbit/s no ar com FEC, 4 dB", lambda: fluxo(DQPSK, 600, 4.0, 1, 425e3), DQPSK, 425e3),
    ("DQPSK 1365 kbit/s no ar com FEC, 6 dB", lambda: fluxo(DQPSK, 600, 6.0, 2, 425e3), DQPSK, 425e3),
    ("DBPSK 25,6 kbit/s no ar com FEC (prova-b), 4 dB",
     lambda: fluxo(ConfigModem("dbpsk", "rrc", 80), 80, 4.0, 3, 250e3), ConfigModem("dbpsk", "rrc", 80), 250e3),
    ("DBPSK, payloads de 40/128/200 bytes e curto no fim",
     lambda: tamanhos_variados(ConfigModem("dbpsk", "rrc", 8), 4), ConfigModem("dbpsk", "rrc", 8), 250e3),
    ("DQPSK, payloads de 40/128/200 bytes e curto no fim",
     lambda: tamanhos_variados(ConfigModem("dqpsk", "rrc", 4), 5), ConfigModem("dqpsk", "rrc", 4), 250e3),
]


def main():
    ref = carregar_referencia()
    casos = []
    for nome, gerar, cm, desl in CASOS:
        x = gerar()
        t0 = time.perf_counter()
        novo = receptor.receber(x, ConfigReceptor(cm, FS, desl, fec=True, guardar_bits=True))
        t1 = time.perf_counter()
        velho = ref.receber(x, ref.ConfigReceptor(cm, FS, desl, fec=True, guardar_bits=True))
        t2 = time.perf_counter()
        iguais = len(novo) == len(velho) and all(
            a.inicio == b.inicio and a.situacao == b.situacao and a.pacote == b.pacote
            and (a.bits is None) == (b.bits is None) and (a.bits is None or np.array_equal(a.bits, b.bits))
            for a, b in zip(novo, velho)
        )
        duracao = len(x) / FS
        casos.append({
            "caso": nome, "deteccoes": len(novo), "aceitos": len(receptor.pacotes_aceitos(novo)),
            "identicos": iguais, "rx_s_por_s": [round((t1 - t0) / duracao, 2), round((t2 - t1) / duracao, 2)],
            "aceleracao": round((t2 - t1) / (t1 - t0), 1),
        })
        print(json.dumps(casos[-1], ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "Viterbi em lote contra um quadro por vez", "referencia": TAG_REFERENCIA,
        "casos": casos, "todos_identicos": all(c["identicos"] for c in casos),
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    print("todos idênticos:", resultado["todos_identicos"])
    saida = RAIZ / "dados" / "logs" / f"viterbi_lote_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

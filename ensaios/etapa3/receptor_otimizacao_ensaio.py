"""Receptor otimizado contra o receptor de referência (o da tag bloco-05-software), nas mesmas capturas.

Duas partes:
1. Equivalência: 9 capturas simuladas (DBPSK, GFSK, OOK, CPFSK retangular; 7 a 13 dB;
   400 quadros com o payload conhecido do BER; offset de −1,4 kHz; atraso de 0,37
   amostra; pico de DC). Compara detecções, instantes, offsets, situação de cada
   quadro, bits demodulados, pacotes aceitos e BER.
2. Tempo: captura de prova simulada de 4 s (quadros um atrás do outro, 12 dB) em
   três configurações, nas duas versões.

O receptor de referência é lido do git (`git show bloco-05-software:sdrlink/receptor.py`)
e roda com os demais módulos atuais.

Uso: python ensaios/etapa3/receptor_otimizacao_ensaio.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from sdrlink import canal, metricas, receptor, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
TAG_REFERENCIA = "bloco-05-software"
FS = 2.048e6
DESLOCAMENTO = 250e3
BITS_COMPARADOS = 1064  # sync + comprimento + sequência + 128 bytes + CRC
CASOS = [
    (("dbpsk", "rrc", 8), (7.0, 10.0)),
    (("fsk", "gaussiano", 16), (10.0, 13.0)),
    (("ook", "rrc", 16), (10.0, 13.0)),
    (("dbpsk", "rrc", 200), (7.0, 10.0)),
    (("fsk", "retangular", 32), (11.0,)),
]
TEMPOS = {
    "DBPSK 256 kbit/s": ("dbpsk", "rrc", 8),
    "GFSK 128 kbit/s": ("fsk", "gaussiano", 16),
    "DBPSK 10,24 kbit/s": ("dbpsk", "rrc", 200),
}


def carregar_referencia():
    """Módulo receptor da tag de referência, importado de um arquivo temporário."""
    fonte = subprocess.run(
        ["git", "show", f"{TAG_REFERENCIA}:sdrlink/receptor.py"],
        cwd=RAIZ, capture_output=True, check=True, text=True, encoding="utf-8",
    ).stdout
    pasta = Path(tempfile.mkdtemp())
    arquivo = pasta / "receptor_referencia.py"
    arquivo.write_text(fonte, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("receptor_referencia", arquivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["receptor_referencia"] = modulo  # as dataclasses precisam do módulo registrado
    spec.loader.exec_module(modulo)
    return modulo


def cronometrar(funcao, *args, **kwargs):
    """Resultado e tempo de execução em segundos."""
    t0 = time.perf_counter()
    resultado = funcao(*args, **kwargs)
    return resultado, time.perf_counter() - t0


def equivalencia(ref, mod, pulso, sps, ebn0):
    """Uma captura simulada recebida pelas duas versões."""
    cm = ConfigModem(mod, pulso, sps)
    rng = np.random.default_rng(int(ebn0 * 10) + sps)
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(400)])
    blocos = transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, DESLOCAMENTO), 1.5)
    s = np.concatenate([b for b, _ in blocos]).astype(complex)
    x = canal.atrasar(np.concatenate([np.zeros(450_000), s]), 0.37)
    x = canal.awgn(canal.girar(x, -1400.0, FS), ebn0, sps, rng)
    x = x + 0.3 * np.sqrt(np.mean(np.abs(s) ** 2))  # pico de DC
    novo, t_novo = cronometrar(receptor.receber, x, ConfigReceptor(cm, FS, DESLOCAMENTO, guardar_bits=True))
    velho, t_velho = cronometrar(ref.receber, x, ref.ConfigReceptor(cm, FS, DESLOCAMENTO, guardar_bits=True))
    pares = list(zip(novo, velho))
    completos = [
        (a.bits[:BITS_COMPARADOS], b.bits[:BITS_COMPARADOS]) for a, b in pares
        if a.bits is not None and b.bits is not None and min(len(a.bits), len(b.bits)) >= BITS_COMPARADOS
    ]
    periodo = transmissor.amostras_por_quadro(cm)
    return {
        "caso": f"{mod}/{pulso} sps {sps} {ebn0:.0f} dB",
        "deteccoes": [len(novo), len(velho)],
        "diferenca_maxima_instante_amostras": round(max(abs(a.inicio - b.inicio) for a, b in pares), 4),
        "diferenca_maxima_offset_hz": round(max(abs(a.offset_hz - b.offset_hz) for a, b in pares), 3),
        "situacao_diferente": sum(a.situacao != b.situacao for a, b in pares),
        "quadros_com_bits_comparados": len(completos),
        "bits_diferentes": int(sum(np.sum(a != b) for a, b in completos)),
        "pacotes_aceitos_iguais": receptor.pacotes_aceitos(novo) == ref.pacotes_aceitos(velho),
        "ber": [metricas.medir_ber(d, periodo, 2 * sps)["ber"] for d in (novo, velho)],
        "tempo_s": [round(t_novo, 2), round(t_velho, 2)],
    }


def tempo_de_prova(ref, mod, pulso, sps):
    """Segundos de processamento por segundo de captura, nas duas versões."""
    cm = ConfigModem(mod, pulso, sps)
    rng = np.random.default_rng(1)
    pacotes = transmissor.numerar([rng.integers(0, 256, 128, dtype=np.uint8).tobytes() for _ in range(3000)])
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, DESLOCAMENTO), 4.0)])
    x = canal.girar(np.concatenate([np.zeros(300_000), s.astype(complex)]), -1400.0, FS)
    x = canal.awgn(x, 12.0, sps, rng).astype(np.complex64)
    duracao = len(x) / FS
    novo, t_novo = cronometrar(receptor.receber, x, ConfigReceptor(cm, FS, DESLOCAMENTO))
    velho, t_velho = cronometrar(ref.receber, x, ref.ConfigReceptor(cm, FS, DESLOCAMENTO))
    return {
        "duracao_s": round(duracao, 2),
        "aceitos": [len(receptor.pacotes_aceitos(novo)), len(ref.pacotes_aceitos(velho))],
        "s_por_s": [round(t_novo / duracao, 2), round(t_velho / duracao, 2)],  # = minutos para 60 s
        "aceleracao": round(t_velho / t_novo, 1),
    }


def main():
    ref = carregar_referencia()
    casos = []
    for (mod, pulso, sps), ebs in CASOS:
        for ebn0 in ebs:
            casos.append(equivalencia(ref, mod, pulso, sps, ebn0))
            print(json.dumps(casos[-1], ensure_ascii=False), flush=True)
    tempos = {}
    for nome, (mod, pulso, sps) in TEMPOS.items():
        tempos[nome] = tempo_de_prova(ref, mod, pulso, sps)
        print(nome, json.dumps(tempos[nome], ensure_ascii=False), flush=True)
    resultado = {
        "referencia": TAG_REFERENCIA,
        "equivalencia": casos,
        "todos_equivalentes": all(
            c["deteccoes"][0] == c["deteccoes"][1] and c["situacao_diferente"] == 0
            and c["bits_diferentes"] == 0 and c["pacotes_aceitos_iguais"] and c["ber"][0] == c["ber"][1]
            for c in casos
        ),
        "tempo_de_prova": tempos,
        "versao_do_codigo": versao_do_codigo(),
    }
    print("todos equivalentes:", resultado["todos_equivalentes"])
    saida = RAIZ / "dados" / "logs" / f"receptor_otimizacao_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

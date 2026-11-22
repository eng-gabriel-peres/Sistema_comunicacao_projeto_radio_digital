"""Ensaio de prova simulado, de ponta a ponta, com os comandos reais (sem hardware).

    payloads.bin -> scripts/transmitir.py --simular -> canal simulado -> scripts/receber.py
                 -> sdrlink.metricas (log do TX × saída do RX) -> PER e goodput

O canal põe 0,3 s de silêncio antes, offset residual de -1,4 kHz (dentro do medido
em 04/11, achado A18), atraso fracionário de 0,37 amostra, ganho de 0,05 e ruído
branco no Eb/N0 pedido (calculado sobre a potência do sinal, não do silêncio).

Janela de 10 s (60 s simulados ocupariam cerca de 1 GB por etapa); o tempo de
processamento é medido para estimar os 60 s da prova.

Uso: python ensaios/etapa3/enlace_simulado_ensaio.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import canal, metricas
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "dados" / "capturas" / "enlace_simulado"
FS = 2.048e6
JANELA_S = 10.0
OFFSET_HZ = -1400.0
SEMENTE = 20261124
CASOS = [  # (nome, modulação, pulso, taxa de bits, Eb/N0 em dB)
    ("DBPSK 256 kbit/s, 12 dB", "dbpsk", "rrc", 256e3, 12.0),
    ("DBPSK 256 kbit/s, 10 dB", "dbpsk", "rrc", 256e3, 10.0),
    ("GFSK 128 kbit/s, 15 dB", "fsk", "gaussiano", 128e3, 15.0),
    ("OOK 128 kbit/s, 15 dB", "ook", "rrc", 128e3, 15.0),
]


def rodar(comando):
    """Roda um script do projeto e devolve o tempo gasto; para se ele falhar."""
    t0 = time.time()
    r = subprocess.run([sys.executable, *comando], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"{comando[0]} falhou:\n{r.stdout}\n{r.stderr}")
    print("   ", r.stdout.strip().replace("\n", "\n    "), flush=True)
    return time.time() - t0


def canal_simulado(entrada, saida, ebn0_db, sps, rng):
    sinal = np.load(entrada).astype(np.complex128)
    ativo = np.abs(sinal) > 0
    pot = np.mean(np.abs(sinal[ativo]) ** 2)  # potência só onde há sinal
    x = np.concatenate([np.zeros(int(0.3 * FS)), sinal])
    x = 0.05 * canal.girar(canal.atrasar(x, 0.37), OFFSET_HZ, FS)
    n0 = 0.05**2 * pot * sps / 10 ** (ebn0_db / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    np.save(saida, x.astype(np.complex64))


def main():
    rng = np.random.default_rng(SEMENTE)
    PASTA.mkdir(parents=True, exist_ok=True)
    payloads = PASTA / "payloads.bin"
    payloads.write_bytes(rng.integers(0, 256, 128 * 5000, dtype=np.uint8).tobytes())  # 5000 pacotes de 128 B
    resultado = {}
    for nome, mod, pulso, rb, ebn0 in CASOS:
        print(nome, flush=True)
        base = PASTA / nome.split(",")[0].replace(" ", "_").replace("/", "")
        logs = PASTA / "logs"
        t_tx = rodar(["scripts/transmitir.py", str(payloads), "--modulacao", mod, "--pulso", pulso, "--taxa-bits", str(rb),
                      "--duracao-s", str(JANELA_S), "--simular", str(base) + "_tx.npy", "--pasta", str(logs)])
        log_tx = sorted(logs.glob("tx_*.txt"), key=lambda p: p.stat().st_mtime)[-1]
        captura = Path(str(base) + f"_{ebn0:.0f}dB.npy")
        canal_simulado(str(base) + "_tx.npy", captura, ebn0, round(FS / rb), rng)
        t_rx = rodar(["scripts/receber.py", str(captura), "--modulacao", mod, "--pulso", pulso, "--taxa-bits", str(rb)])
        saida_rx = captura.with_name(captura.stem + "_saida.txt")
        r = metricas.avaliar(metricas.ler_pacotes(log_tx), metricas.ler_pacotes(saida_rx), JANELA_S)
        rx_json = json.loads(captura.with_name(captura.stem + "_rx.json").read_text(encoding="utf-8"))
        r.update({
            "tempo_tx_s": round(t_tx, 1), "tempo_rx_s": round(t_rx, 1),
            "tempo_rx_estimado_60s_min": round(t_rx * 60 / JANELA_S / 60, 1),
            "offset_estimado_hz": rx_json["offset_residual_mediano_hz"], "deteccoes": rx_json["deteccoes"],
            "crc_falho": rx_json["crc_falho"],
        })
        resultado[nome] = r
        print("   ", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
        for arquivo in (Path(str(base) + "_tx.npy"), captura):
            arquivo.unlink()  # centenas de MB cada; os logs e as saídas ficam
    registro = {"ensaio": "prova simulada de ponta a ponta com os comandos reais", "versao_do_codigo": versao_do_codigo(),
                "janela_s": JANELA_S, "offset_hz": OFFSET_HZ, "semente": SEMENTE, "resultado": resultado}
    saida = RAIZ / "dados" / "logs" / f"enlace_simulado_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

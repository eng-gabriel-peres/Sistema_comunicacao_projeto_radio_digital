"""Ensaio geral da prova A sem hardware: 60 s com os comandos da prova e o perfil prova-a.

    gerar_payloads.py --aleatorios -> transmitir.py --perfil prova-a --simular
    -> canal (em blocos: offset, imagem IQ, DC, ruído) -> receber.py --perfil prova-a
    -> avaliar.py --duracao-s 60

Mede o que a prova cobra: PER, goodput, banda a 99% na captura e o tempo de
processamento do RX (limite de 10 min). A captura tem 1 s de ruído antes do TX e
0,5 s depois, como na gravação real (começar antes, parar depois).

A captura de 60 s ocupa cerca de 1 GB em complex64; o canal trabalha em blocos e
grava direto no arquivo. Os .npy são apagados no fim; logs e saídas ficam.

Uso: python ensaios/etapa6/prova_a_60s_ensaio.py [Eb/N0 em dB, padrão 11] [perfil, padrão prova-a]

O Eb/N0 é por bit no ar: na DQPSK, Eb = Es/2.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import config
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / "dados" / "capturas" / "prova_a_60s"
PERFIL = "prova-a"
DURACAO_S = 60.0
ANTES_S, DEPOIS_S = 1.0, 0.5
OFFSET_HZ = -1400.0
DC_RELATIVO = 0.008
IMAGEM_DBC = -45.0
BLOCO = 2**22
PAYLOADS = 100_000  # mais do que cabe em 60 s: 36 500 na DBPSK, 70 400 na DQPSK (com 60 000 o TX
# da DQPSK ficou sem payloads aos 51 s; na prova, conferir o tamanho do arquivo do avaliador)
SEMENTE = 20261122
LIMITE_RX_S = 600.0


def rodar(*comando):
    """Roda um script do projeto; devolve o tempo e a saída. Para se ele falhar."""
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, *comando], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"{comando[0]} falhou:\n{r.stdout}\n{r.stderr}")
    print("   ", r.stdout.strip().replace("\n", "\n    "), flush=True)
    return time.perf_counter() - t0


def canal_em_blocos(entrada, saida, ebn0_db, amostras_por_bit, fs, rng):
    """Canal com os defeitos medidos do RTL, bloco a bloco, com fase contínua."""
    tx = np.load(entrada, mmap_mode="r")
    ativos = np.flatnonzero(np.abs(tx[-BLOCO:]) > 0)  # o fim do fluxo é completado com zeros
    fim = len(tx) - BLOCO + int(ativos[-1]) + 1 if len(ativos) else len(tx)
    potencia = float(np.mean([np.mean(np.abs(tx[k : min(k + BLOCO, fim)]) ** 2) for k in range(0, fim, BLOCO)]))
    n0 = potencia * amostras_por_bit / 10 ** (ebn0_db / 10)
    antes, depois = int(ANTES_S * fs), int(DEPOIS_S * fs)
    total = antes + fim + depois
    y = np.lib.format.open_memmap(saida, mode="w+", dtype=np.complex64, shape=(total,))
    dc = DC_RELATIVO * np.sqrt(potencia + n0)
    imagem = 10 ** (IMAGEM_DBC / 20)
    for k in range(0, total, BLOCO):
        n = min(BLOCO, total - k)
        x = np.zeros(n, dtype=complex)
        a, b = max(k, antes), min(k + n, antes + fim)
        if b > a:
            x[a - k : b - k] = tx[a - antes : b - antes]
        x = x * np.exp(2j * np.pi * OFFSET_HZ / fs * np.arange(k, k + n))
        x = x + imagem * np.conj(x)
        x = x + np.sqrt(n0 / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n)) + dc
        y[k : k + n] = x.astype(np.complex64)
    y.flush()
    return total / fs


def main():
    ebn0 = float(sys.argv[1]) if len(sys.argv) > 1 else 11.0
    nome_perfil = sys.argv[2] if len(sys.argv) > 2 else PERFIL
    perfil = config.perfil(nome_perfil)
    rng = np.random.default_rng(SEMENTE)
    PASTA.mkdir(parents=True, exist_ok=True)
    logs = PASTA / "logs"
    payloads, tx = PASTA / "payloads.bin", PASTA / "tx.npy"
    cap = PASTA / f"{nome_perfil.replace('-', '_')}_{ebn0:.0f}dB.npy"
    print(f"perfil {nome_perfil}: {perfil.taxa_bits / 1e3:.1f} kbit/s, Eb/N0 {ebn0} dB", flush=True)
    rodar("scripts/gerar_payloads.py", "--aleatorios", str(PAYLOADS), str(payloads), "--semente", str(SEMENTE))
    t_tx = rodar("scripts/transmitir.py", str(payloads), "--perfil", nome_perfil, "--duracao-s", str(DURACAO_S),
                 "--simular", str(tx), "--pasta", str(logs))
    log_tx = sorted(logs.glob("tx_*.txt"), key=lambda p: p.stat().st_mtime)[-1]
    t0 = time.perf_counter()
    amostras_por_bit = perfil.sps / perfil.modem().bits_por_simbolo
    duracao_captura = canal_em_blocos(tx, cap, ebn0, amostras_por_bit, perfil.taxa_sps, rng)
    t_canal = time.perf_counter() - t0
    t_rx = rodar("scripts/receber.py", str(cap), "--perfil", nome_perfil)
    saida_rx = cap.with_name(cap.stem + "_saida.txt")
    rodar("scripts/avaliar.py", str(log_tx), str(saida_rx), "--duracao-s", str(DURACAO_S))
    avaliacao = json.loads(saida_rx.with_name(saida_rx.stem + "_avaliacao.json").read_text(encoding="utf-8"))
    rx = json.loads(cap.with_name(cap.stem + "_rx.json").read_text(encoding="utf-8"))
    tx_json = json.loads(log_tx.with_suffix(".json").read_text(encoding="utf-8"))
    medidas = rx["medidas_da_captura"]
    resultado = {
        "ensaio": "prova A simulada de ponta a ponta, 60 s, comandos da prova",
        "perfil": rx["perfil"], "ebn0_db": ebn0, "offset_hz": OFFSET_HZ, "dc_relativo": DC_RELATIVO,
        "imagem_dbc": IMAGEM_DBC, "semente": SEMENTE, "duracao_da_captura_s": round(duracao_captura, 2),
        "transmitidos": avaliacao["transmitidos"], "recebidos_certos": avaliacao["recebidos_certos"],
        "per": avaliacao["per"], "goodput_kbps": round(avaliacao["goodput_bps"] / 1e3, 1),
        "conteudo_diferente": avaliacao["conteudo_diferente"], "espurios": avaliacao["espurios"],
        "banda_99_medida_khz": medidas.get("banda_99_khz"), "ebn0_medido_db": medidas.get("ebn0_estimado_db"),
        "tempo_tx_simulado_s": round(t_tx, 1), "tx_tempo_real_registrado_s": tx_json["tempo_real_s"],
        "tempo_canal_s": round(t_canal, 1), "tempo_rx_total_s": round(t_rx, 1),
        "tempo_rx_processamento_s": rx["tempo_de_processamento_s"],
        "dentro_dos_10_min": t_rx < LIMITE_RX_S,
        "passa_na_prova_a": avaliacao["per"] <= 0.01 and (medidas.get("banda_99_khz") or 1e9) <= 1000,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),  # saídas e texto: não mudam o que roda
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    saida = RAIZ / "dados" / "logs" / f"{nome_perfil.replace('-', '_')}_60s_{ebn0:.0f}dB_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for arquivo in (tx, cap):
        arquivo.unlink()
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

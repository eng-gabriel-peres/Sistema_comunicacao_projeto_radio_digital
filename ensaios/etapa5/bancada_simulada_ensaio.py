"""Etapa 5: ensaio geral da sessão de bancada, com a captura simulada no lugar do RTL.

Roda exatamente os scripts que vão ser usados na bancada, na ordem do plano de bancada:
    gerar_payloads.py --conhecidos   (uma vez)
    transmitir.py --simular          (o sinal que o Pluto mandaria, com o log do TX)
    [aqui entraria o gravar_iq.py: a captura é montada a partir do sinal do TX, com
     0,5 s de ruído antes, offset de −1,4 kHz, atraso fracionário, DC e ruído no Eb/N0 pedido,
     e um JSON de metadados como o do gravar_iq.py]
    receber.py --ber                 (saída, BER, banda e Eb/N0 medidos na captura)
    avaliar.py                       (PER e goodput pelo log do TX)
    analisar_bancada.py              (tabela, gráficos e perda do enlace)
O que se confere: a cadeia fecha sem intervenção manual, o Eb/N0 medido bate com o
verdadeiro e a perda do enlace em relação à teoria fica pequena (só a perda de
implementação do receptor, porque o canal é AWGN).

Uso: python ensaios/etapa5/bancada_simulada_ensaio.py   (cerca de 5 min)
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from sdrlink import bancada, canal, config
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
DURACAO_S = 2.0
RUIDO_S = 0.5
OFFSET_HZ = -1400.0
PONTOS = {
    "dbpsk-256k": (7.0, 9.0, 11.0),
    "gfsk-128k": (10.0, 12.0, 14.0),
    "ook-128k": (10.0, 12.0, 14.0),
    "prova-b": (4.0, 5.0, 6.0),
}
SEMENTE = 20261122


def rodar(script, *argumentos):
    """Roda um script do projeto como na bancada; para tudo se ele falhar."""
    r = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / script), *map(str, argumentos)],
        capture_output=True, text=True, encoding="utf-8", cwd=RAIZ, check=False,
        env={**os.environ, "PYTHONPATH": str(RAIZ), "PYTHONIOENCODING": "utf-8"},
    )
    if r.returncode != 0:
        raise SystemExit(f"{script} falhou:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def capturar(tx_npy, perfil, ebn0_db, destino, rng):
    """Monta a captura que o RTL gravaria a partir do sinal do TX, com o JSON de metadados."""
    sinal = np.load(tx_npy).astype(np.complex128)
    ativo = sinal[np.abs(sinal) > 0]
    potencia = float(np.mean(np.abs(ativo) ** 2))
    fs = perfil.taxa_sps
    x = np.concatenate([np.zeros(int(RUIDO_S * fs)), canal.girar(canal.atrasar(sinal, 0.37), OFFSET_HZ, fs)])
    n0 = potencia * (fs / perfil.taxa_bits) / 10 ** (ebn0_db / 10)  # Eb = P · amostras por bit
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    x = x + 0.3 * np.sqrt(potencia)  # pico de DC do RTL
    np.save(destino, x.astype(np.complex64))
    metadados = {
        "simulada": True, "ebn0_verdadeiro_db": ebn0_db, "centro_hz": perfil.lo_hz, "taxa_sps": fs,
        "ganho_db": None, "fracao_saturada": 0.0, "amostras": len(x),
    }
    destino.with_suffix(".json").write_text(json.dumps(metadados, indent=2) + "\n", encoding="utf-8")


def main():
    carimbo = carimbo_de_tempo()
    sessao = RAIZ / "dados" / "capturas" / f"sessao_simulada_{carimbo}"  # capturas: fora do git
    sessao.mkdir(parents=True)
    payloads = sessao / "payloads_ber.bin"
    rodar("gerar_payloads.py", "--conhecidos", 4000, payloads)
    rng = np.random.default_rng(SEMENTE)
    verdade = {}
    for nome, ebn0s in PONTOS.items():
        perfil = config.perfil(nome)
        for ebn0 in ebn0s:
            ponto = f"{nome}_{ebn0:04.1f}dB"
            pasta_tx = sessao / f"tx_{ponto}"
            tx_npy = pasta_tx / "sinal_tx.npy"
            rodar("transmitir.py", payloads, "--perfil", nome, "--duracao-s", DURACAO_S,
                  "--simular", tx_npy, "--pasta", pasta_tx)
            captura = sessao / f"{ponto}.npy"
            capturar(tx_npy, perfil, ebn0, captura, rng)
            rodar("receber.py", captura, "--perfil", nome, "--ber")
            log_tx = next(pasta_tx.glob("tx_*.txt"))
            print(rodar("avaliar.py", log_tx, sessao / f"{ponto}_saida.txt", "--duracao-s", DURACAO_S).strip())
            verdade[f"{ponto}.npy"] = ebn0
            captura.unlink()  # a análise só precisa dos registros
            tx_npy.unlink()
    print(rodar("analisar_bancada.py", sessao).strip())
    pontos = bancada.ler_sessao(sessao)
    erros_ebn0 = [p.ebn0_db - verdade[p.captura] for p in pontos if p.ebn0_db is not None]
    perdas = {p.captura: bancada.perda_db(p) for p in pontos}
    evidencia = RAIZ / "dados" / "logs" / f"bancada_simulada_{carimbo}"
    evidencia.mkdir(parents=True)
    for arquivo in sorted(sessao.iterdir()):
        if arquivo.suffix in (".json", ".md", ".png") or arquivo.name.endswith("_saida.txt"):
            shutil.copy2(arquivo, evidencia / arquivo.name)
    resultado = {
        "ensaio": "sessão de bancada simulada (scripts da bancada de ponta a ponta)",
        "duracao_por_ponto_s": DURACAO_S,
        "pontos": [
            {
                "captura": p.captura, "perfil": p.perfil, "ebn0_verdadeiro_db": verdade[p.captura],
                "ebn0_medido_db": p.ebn0_db, "ber": p.ber, "bits_comparados": p.bits_comparados,
                "per": p.per, "goodput_bps": p.goodput_bps, "banda_khz": p.banda_khz,
                "perda_db": None if perdas[p.captura] is None else round(perdas[p.captura], 2),
            }
            for p in pontos
        ],
        "erro_do_ebn0_medido_db": {
            "mediana": round(float(np.median(erros_ebn0)), 2),
            "maximo_absoluto": round(float(np.max(np.abs(erros_ebn0))), 2),
        },
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"bancada_simulada_{carimbo}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for p in resultado["pontos"]:
        print(f"{p['captura']}: Eb/N0 {p['ebn0_verdadeiro_db']} -> {p['ebn0_medido_db']} dB, "
              f"BER {p['ber']}, PER {p['per']}, perda {p['perda_db']}")
    print(json.dumps(resultado["erro_do_ebn0_medido_db"]))
    print(f"registro: {saida}\nevidências da sessão: {evidencia}")


if __name__ == "__main__":
    sys.exit(main())

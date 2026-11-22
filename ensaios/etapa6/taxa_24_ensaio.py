"""Perfil experimental prova-a-24: a DQPSK com o RTL a 2,4 MS/s, a taxa máxima recomendada.

Compara o prova-a-24 com o prova-a (2,048 MS/s) no mesmo canal: 1000 quadros por ponto,
receptor completo, offset de −1,4 kHz, atraso fracionário, DC de 0,008 do valor eficaz,
imagem IQ a −45 dBc. A resposta em frequência do RTL a 2,4 MS/s nunca foi medida: o
ensaio supõe a mesma de 2,048 MS/s (plana até cerca de 0,8 da frequência de Nyquist),
e o sinal fica dentro dessa fração. Depois, a prova de 60 s simulada com o perfil novo.

Uso: python ensaios/etapa6/taxa_24_ensaio.py
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prova_a_ensaio as base  # noqa: E402

from sdrlink import canal, config, metricas, receptor, transmissor  # noqa: E402
from sdrlink.receptor import ConfigReceptor  # noqa: E402
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo  # noqa: E402
from sdrlink.transmissor import ConfigTransmissor  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
QUADROS = 1000
EBN0_DB = np.arange(10.0, 15.5, 1.0)
PERFIS = ("prova-a", "prova-a-24")
EBN0_60S = 14.0


def per(nome, ebn0, semente):
    """PER do perfil com os defeitos do RTL, na taxa de amostragem dele."""
    p = config.perfil(nome)
    cm, fs = p.modem(), p.taxa_sps
    ct = ConfigTransmissor(cm, fs, p.deslocamento_hz, emendar_caudas=p.emendar_caudas)
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(QUADROS)])
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, ct, 1e3)]).astype(complex)
    s = s[: np.flatnonzero(s)[-1] + 1]
    margem = np.zeros(int(0.1 * fs))
    rng = np.random.default_rng(semente)
    x = canal.girar(canal.atrasar(np.concatenate([margem, s, margem]), 0.37), base.OFFSET_HZ, fs)
    x = x + 10 ** (base.IMAGEM_DBC / 20) * np.conj(x)
    n0 = np.mean(np.abs(s) ** 2) * cm.sps / cm.bits_por_simbolo / 10 ** (ebn0 / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    x = x + base.DC_RELATIVO * np.sqrt(np.mean(np.abs(x) ** 2))
    d = receptor.receber(x, ConfigReceptor(cm, fs, p.deslocamento_hz))
    aceitos = receptor.pacotes_aceitos(d)
    certos = sum(q.sequencia < QUADROS and q.payload == metricas.payload_conhecido(q.sequencia) for q in aceitos)
    return 1 - certos / QUADROS


def main():
    cn0 = base.cn0_da_bancada()
    linhas = []
    for nome in PERFIS:
        p = config.perfil(nome)
        cm = p.modem()
        valores = [per(nome, e, 2000 + k) for k, e in enumerate(EBN0_DB)]
        necessario = base.ebn0_para_per(EBN0_DB, valores)
        baixo, alto = ConfigTransmissor(cm, p.taxa_sps, p.deslocamento_hz).banda_99_hz()
        periodo = transmissor.amostras_por_quadro(cm, emendar_caudas=p.emendar_caudas)
        cn0_necessario = None if necessario is None else necessario + 10 * np.log10(p.taxa_bits)
        linha = {
            "perfil": nome, "taxa_sps": p.taxa_sps, "taxa_bits": round(p.taxa_bits, 1),
            "banda_99_khz": round((alto - baixo) / 1e3, 1), "faixa_khz": [round(baixo / 1e3, 1), round(alto / 1e3, 1)],
            "goodput_sem_perda_kbps": round(p.taxa_sps * 1024 / periodo / 1e3, 1),
            "per_por_ebn0": {f"{e:.0f}": round(v, 4) for e, v in zip(EBN0_DB, valores)},
            "ebn0_per_1pct_db": None if necessario is None else round(necessario, 2),
            "cn0_necessario_dbhz": None if cn0_necessario is None else round(cn0_necessario, 2),
            "margem_na_bancada_db": None if cn0_necessario is None else round(cn0 - cn0_necessario, 1),
        }
        linhas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    r = subprocess.run([sys.executable, "ensaios/etapa6/prova_a_60s_ensaio.py", str(EBN0_60S), "prova-a-24"],
                       cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stdout + r.stderr)
    registro_60s = r.stdout.strip().splitlines()[-1].split("registro: ")[1]
    dados = json.loads(Path(registro_60s).read_text(encoding="utf-8"))
    prova = {k: dados[k] for k in ("transmitidos", "recebidos_certos", "per", "goodput_kbps", "conteudo_diferente",
                                    "banda_99_medida_khz", "tempo_rx_processamento_s")}
    prova["registro"] = Path(registro_60s).name
    print(json.dumps(prova, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "perfil experimental a 2,4 MS/s contra o prova-a", "cn0_bancada_dbhz": round(cn0, 1),
        "quadros_por_ponto": QUADROS, "perfis": linhas, "prova_60s": prova,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"taxa_24_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

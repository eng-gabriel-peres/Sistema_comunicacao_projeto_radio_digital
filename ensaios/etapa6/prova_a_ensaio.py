"""Prova A em simulação: qual taxa dá o maior goodput com PER de até 1% e banda de até 1 MHz.

Para cada candidata (DBPSK RRC a 2,048 MS/s, de 8 a 2 amostras por bit):
1. banda a 99% do sinal transmitido;
2. PER do receptor completo × Eb/N0 (1000 quadros de 128 bytes por ponto, quadros
   um atrás do outro como na prova), com os defeitos do enlace real medidos na
   captura de 04/11: offset de −1,4 kHz, atraso fracionário, DC de 0,008 do valor
   eficaz e imagem IQ a −45 dBc;
3. Eb/N0 para PER de 1% (interpolação em log da PER) e margem diante do C/N0 da
   bancada de 04/11 (78,2 dB-Hz, medido na captura ook_ref_continua16s);
4. tempo do TX (fração do tempo real) e do RX (segundos por segundo de captura).

Mais a escolha do fator de rolagem na candidata de 3 amostras por bit.

Uso: python ensaios/etapa6/prova_a_ensaio.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import welch

from sdrlink import canal, metricas, receptor, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
CAPTURA_BANCADA = RAIZ / "dados" / "capturas" / "ook_ref_continua16s_20261104_103841.npy"
FS = 2.048e6
QUADROS = 1000
EBN0_DB = np.arange(5.0, 12.5, 1.0)
OFFSET_HZ = -1400.0
DC_RELATIVO = 0.008  # medido na captura real (|média| / valor eficaz)
IMAGEM_DBC = -45.0  # medida na captura real
DISTANCIA_DO_DC_HZ = 50e3
BANDA_MAX_HZ = 1e6
PER_ALVO = 0.01
BITS_UTEIS = 1024  # 128 bytes de payload por quadro
CANDIDATAS = [(8, 0.35), (6, 0.25), (4, 0.25), (3, 0.25), (2, 0.25)]  # (sps, beta)
BETAS_SPS3 = (0.2, 0.25, 0.35)


def cn0_da_bancada():
    """C/N0 da captura real de 04/11: potência do sinal acima do piso, dividida pelo piso."""
    x = np.asarray(np.load(CAPTURA_BANCADA, mmap_mode="r")[: int(4 * FS)], dtype=complex)
    f, p = welch(x - x.mean(), fs=FS, nperseg=8192, return_onesided=False)
    ordem = np.argsort(f)
    f, p = f[ordem], p[ordem]
    piso = np.median(p[np.abs(f + 500e3) < 150e3])
    banda = (f > 150e3) & (f < 250e3)  # OOK da referência em +200 kHz, 10 kbit/s
    sinal = np.sum(p[banda] - piso) * (f[1] - f[0])
    return float(10 * np.log10(sinal / piso))


def deslocamento(cm):
    """Põe a borda inferior da banda a 99% a 50 kHz do DC (no mínimo 250 kHz, como antes)."""
    baixo, alto = ConfigTransmissor(cm, FS, 0.0).banda_99_hz()
    return max(250e3, float(np.ceil((DISTANCIA_DO_DC_HZ - baixo) / 5e3) * 5e3)), alto - baixo


def defeitos_do_rtl(x, rng):
    """Offset, atraso fracionário, imagem IQ e DC, nos valores medidos."""
    y = canal.girar(canal.atrasar(x, 0.37), OFFSET_HZ, FS, rng.uniform(0, 2 * np.pi))
    y = y + 10 ** (IMAGEM_DBC / 20) * np.conj(y)
    return y


def captura(cm, desl, ebn0_db, rng, quadros=QUADROS):
    """Quadros um atrás do outro, 0,1 s de ruído antes, com os defeitos do RTL e ruído."""
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(quadros)])
    blocos = transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, desl), 1e3)
    s = np.concatenate([b for b, _ in blocos]).astype(complex)
    s = s[: np.flatnonzero(s)[-1] + 1]
    potencia = np.mean(np.abs(s) ** 2)
    x = defeitos_do_rtl(np.concatenate([np.zeros(int(0.1 * FS)), s]), rng)
    n0 = potencia * cm.sps / 10 ** (ebn0_db / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    return x + DC_RELATIVO * np.sqrt(np.mean(np.abs(x) ** 2)), quadros


def per_do_receptor(cm, desl, ebn0_db, rng):
    """PER, pacotes errados aceitos e tempo de processamento por segundo de captura."""
    x, quadros = captura(cm, desl, ebn0_db, rng)
    t0 = time.perf_counter()
    aceitos = receptor.pacotes_aceitos(receptor.receber(x, ConfigReceptor(cm, FS, desl)))
    tempo = time.perf_counter() - t0
    certos = sum(p.sequencia < quadros and p.payload == metricas.payload_conhecido(p.sequencia) for p in aceitos)
    return 1 - certos / quadros, len(aceitos) - certos, tempo / (len(x) / FS)


def ebn0_para_per(ebn0, per):
    """Eb/N0 em que a PER cruza 1%, interpolando log10(PER) entre os pontos vizinhos."""
    for k in range(1, len(per)):
        if per[k] <= PER_ALVO < per[k - 1]:
            a, b = np.log10(max(per[k - 1], 1e-4)), np.log10(max(per[k], 1e-4))
            return float(ebn0[k - 1] + (np.log10(PER_ALVO) - a) / (b - a) * (ebn0[k] - ebn0[k - 1]))
    return None


def tempo_do_tx(cm, desl):
    """Fração do tempo real que o TX leva para gerar 4 s de fluxo."""
    pacotes = transmissor.numerar([bytes(128)] * 20000)
    t0 = time.perf_counter()
    n = sum(len(b) for b, _ in transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, desl), 4.0))
    return (time.perf_counter() - t0) / (n / FS)


def main():
    cn0 = cn0_da_bancada()
    print(f"C/N0 da bancada de 04/11: {cn0:.1f} dB-Hz", flush=True)
    rng = np.random.default_rng(20261122)
    candidatas = []
    for sps, beta in CANDIDATAS:
        cm = ConfigModem("dbpsk", "rrc", sps, beta=beta)
        desl, banda = deslocamento(cm)
        rb = FS / sps
        linha = {"sps": sps, "beta": beta, "taxa_bits": round(rb, 1), "banda_99_khz": round(banda / 1e3, 1),
                 "deslocamento_khz": desl / 1e3, "cabe_em_1_mhz": bool(banda <= BANDA_MAX_HZ)}
        if banda <= BANDA_MAX_HZ:
            pontos = [per_do_receptor(cm, desl, e, rng) for e in EBN0_DB]
            per = [p for p, _, _ in pontos]
            necessario = ebn0_para_per(EBN0_DB, per)
            disponivel = cn0 - 10 * np.log10(rb)
            linha.update({
                "per_por_ebn0": {f"{e:.0f}": round(p, 4) for e, p in zip(EBN0_DB, per)},
                "errados_aceitos": int(sum(e for _, e, _ in pontos)),
                "ebn0_per_1pct_db": None if necessario is None else round(necessario, 2),
                "ebn0_na_bancada_db": round(disponivel, 1),
                "margem_db": None if necessario is None else round(disponivel - necessario, 1),
                # período real do quadro no fluxo: 1 109 bits mais a cauda do pulso (13 bits no RRC)
                "bits_por_quadro_no_fluxo": round(transmissor.amostras_por_quadro(cm) / sps, 1),
                "goodput_sem_perda_kbps": round(FS * BITS_UTEIS / transmissor.amostras_por_quadro(cm) / 1e3, 1),
                "rx_s_por_s": round(float(np.median([t for _, _, t in pontos])), 2),
                "tx_fracao_do_tempo_real": round(tempo_do_tx(cm, desl), 2),
            })
        candidatas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    betas = []
    for beta in BETAS_SPS3:
        cm = ConfigModem("dbpsk", "rrc", 3, beta=beta)
        desl, banda = deslocamento(cm)
        pontos = {f"{e:.0f}": round(per_do_receptor(cm, desl, e, rng)[0], 4) for e in (7.0, 8.0, 9.0)}
        betas.append({"beta": beta, "banda_99_khz": round(banda / 1e3, 1), "per_por_ebn0": pontos})
        print(json.dumps(betas[-1], ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "prova A em simulação: taxa × banda × PER do receptor completo",
        "taxa_sps": FS, "quadros_por_ponto": QUADROS, "offset_hz": OFFSET_HZ,
        "dc_relativo": DC_RELATIVO, "imagem_dbc": IMAGEM_DBC, "cn0_bancada_dbhz": round(cn0, 1),
        "candidatas": candidatas, "beta_com_3_amostras_por_bit": betas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),  # saídas e texto: não mudam o que roda
    }
    saida = RAIZ / "dados" / "logs" / f"prova_a_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

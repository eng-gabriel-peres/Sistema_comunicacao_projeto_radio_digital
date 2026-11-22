"""FEC com sincronismo ideal: quanto o código ganha sozinho, e quanto a detecção coerente daria.

Sem o receptor: instante, offset e fase do início conhecidos (o "gênio"). Separa o ganho
do código (sdrlink.codigo) das perdas da detecção e da estimativa do receptor real.

Três detectores para a DBPSK, com e sem FEC, por Eb/N0 de bit útil (com FEC, cada bit
no ar leva metade da energia: Eb/N0 no ar = Eb/N0 útil − 3,01 dB):
    diferencial   o do projeto: -Re(z_k conj(z_k-1))
    coerente 16   fase pela média móvel de z² em 16 símbolos (a BPSK some ao quadrado),
    coerente 32   o mesmo em 32 símbolos; os dois com decodificação diferencial
Com um offset que sobra de 0,002 ciclo por símbolo (50 Hz a 25,6 kbit/s), 300 quadros
de 128 bytes por ponto.

Uso: python ensaios/etapa6/fec_sincronismo_ideal_ensaio.py
"""

import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import codigo, metricas, modem, quadro
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
CM = ConfigModem("dbpsk", "rrc", 8)
QUADROS = 300
RESIDUO = 0.002  # ciclos por símbolo
EBN0_UTIL_DB = (5.0, 5.5, 6.0, 6.5, 7.0, 8.0, 9.0, 10.0)
DETECTORES = ("diferencial", "coerente 16", "coerente 32")
TRES_DB = 10 * np.log10(2)
PER_ALVO = 0.01


def suave_coerente(y, n, janela):
    """Fase pela média móvel de z² (desenrolada e dividida por 2), detecção diferencial."""
    z = modem.saida_casada(y, CM, n + 1)
    fase = np.unwrap(np.angle(np.convolve(z**2, np.ones(janela), mode="same"))) / 2
    a = np.real(z * np.exp(-1j * fase))
    return -(a[1:] * a[:-1])


def per(fec, detector, ebn0_util, rng):
    """PER de QUADROS quadros com sincronismo ideal."""
    erros = 0
    for k in range(QUADROS):
        p = Pacote(k, metricas.payload_conhecido(k))
        bits = quadro.montar_quadro(p, fec)
        s = modem.modular(bits, CM)
        s = s * np.exp(2j * np.pi * RESIDUO / CM.sps * np.arange(len(s)) + 1j * rng.uniform(0, 2 * np.pi))
        ebn0_ar = ebn0_util - (TRES_DB if fec else 0.0)
        n0 = np.mean(np.abs(s[: len(bits) * CM.sps]) ** 2) * CM.sps / 10 ** (ebn0_ar / 10)
        y = s + np.sqrt(n0 / 2) * (rng.standard_normal(len(s)) + 1j * rng.standard_normal(len(s)))
        n = len(bits) - len(quadro.GUARDA)
        if detector == "diferencial":
            suaves = modem.demodular_suave(y, CM, n)
        else:
            suaves = suave_coerente(y, n, int(detector.split()[1]))
        corpo = suaves[len(quadro.PREAMBULO) + len(quadro.SYNC) :]  # depois do sync
        if fec:
            info = codigo.decodificar(corpo, quadro.bits_apos_sync(128))
        else:
            info = (corpo > 0).astype(np.uint8)
        erros += quadro.interpretar(info).pacote != p
    return erros / QUADROS


def cruza(ebn0, valores):
    """Eb/N0 em que a PER cruza 1% (interpolação de log10 da PER)."""
    for k in range(1, len(valores)):
        if valores[k] <= PER_ALVO < valores[k - 1]:
            a, b = np.log10(max(valores[k - 1], 1e-4)), np.log10(max(valores[k], 1e-4))
            return round(float(ebn0[k - 1] + (np.log10(PER_ALVO) - a) / (b - a) * (ebn0[k] - ebn0[k - 1])), 2)
    return None


def main():
    rng = np.random.default_rng(20261126)
    curvas = {}
    for fec in (False, True):
        for detector in DETECTORES:
            nome = f"{'com' if fec else 'sem'} FEC, {detector}"
            valores = [per(fec, detector, e, rng) for e in EBN0_UTIL_DB]
            curvas[nome] = {"per": dict(zip((f"{e}" for e in EBN0_UTIL_DB), valores)),
                            "ebn0_util_per_1pct_db": cruza(EBN0_UTIL_DB, valores)}
            print(nome, json.dumps(curvas[nome], ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "FEC com sincronismo ideal: ganho do código e detectores",
        "modem": "dbpsk rrc sps 8", "quadros_por_ponto": QUADROS, "residuo_ciclos_por_simbolo": RESIDUO,
        "curvas": curvas, "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"fec_sincronismo_ideal_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

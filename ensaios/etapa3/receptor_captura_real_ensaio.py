"""Valida o receptor multiquadro (sdrlink.receptor) com a captura real de 16 s da OOK de referência.

A captura de 04/11/2026 (dados/capturas/ook_ref_continua16s_20261104_103841.npy,
Pluto da equipe -> RTL, 84 ppm) tem 698 quadros da OOK do professor, todos com
CRC-8 OK pelo decodificador de 04/11 (docs/etapa2_recepcao_ook.md). O quadro da
referência não tem número de sequência (comprimento 8 bits, payload, CRC-8), então
o receptor recebe um interpretador desse formato; a detecção, a estimativa de
offset e de instante e a demodulação são as do projeto.

O TX da referência usa 200 amostras por bit a 2 MS/s; a captura a 2,048 MS/s é
reamostrada por 125/128 para 2 MS/s (200 amostras por bit exatas).

Uso: python ensaios/etapa3/receptor_captura_real_ensaio.py [captura.npy]
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from sdrlink import quadro, receptor
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Leitura, Pacote
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
CAPTURA = RAIZ / "dados" / "capturas" / "ook_ref_continua16s_20261104_103841.npy"
MENSAGEM = b"HELLO WORLD MANDRIAUM"


def crc8_referencia(dados):
    """CRC-8 do pluto_tx_ook_v2.py (polinômio 0x07, valor inicial 0)."""
    crc = 0
    for byte in dados:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def interpretar_referencia(bits):
    """Quadro da referência depois do sync: comprimento (8), payload, CRC-8 (8)."""
    if len(bits) < 8:
        return Leitura(None, "curto", 0)
    n = int(quadro.bits_para_bytes(bits[:8])[0])
    total = 8 + 8 * n + 8
    if len(bits) < total:
        return Leitura(None, "curto", 0)
    corpo = quadro.bits_para_bytes(bits[:total])
    carga, crc = corpo[1:-1], corpo[-1]
    if crc8_referencia(carga) != crc:
        return Leitura(None, "crc", total)
    return Leitura(Pacote(0, carga), "ok", total)  # sem número de sequência na referência


def main():
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else CAPTURA
    t0 = time.time()
    x = resample_poly(np.load(caminho), 125, 128)  # 2,048 -> 2,0 MS/s
    t_reamostragem = time.time() - t0
    config = ConfigReceptor(ConfigModem("ook", "retangular", 200), 2.0e6, deslocamento_hz=200e3)
    t1 = time.time()
    deteccoes = receptor.receber(x, config, interpretador=interpretar_referencia)
    t_receptor = time.time() - t1
    duracao = len(x) / 2.0e6
    periodo = 229 * 200  # 229 bits por repetição do quadro da referência, 200 amostras por bit
    inicios = np.array([d.inicio for d in deteccoes])
    esperados = int(round((inicios[-1] - inicios[0]) / periodo)) + 1
    situacoes = {s: sum(d.situacao == s for d in deteccoes) for s in ("ok", "crc", "curto")}
    corretos = sum(d.pacote is not None and d.pacote.payload == MENSAGEM for d in deteccoes)
    desvio = np.diff(inicios) - periodo
    resultado = {
        "captura": str(caminho.relative_to(RAIZ)) if caminho.is_relative_to(RAIZ) else str(caminho),
        "duracao_s": round(duracao, 2),
        "deteccoes": len(deteccoes),
        "quadros_esperados_pelo_periodo": esperados,
        "situacoes": situacoes,
        "payload_igual_a_mensagem": corretos,
        "offset_mediano_hz": round(float(np.median([d.offset_hz for d in deteccoes])), 1),
        "offset_p5_p95_hz": [round(float(v), 1) for v in np.percentile([d.offset_hz for d in deteccoes], [5, 95])],
        "metrica_minima": round(min(d.metrica for d in deteccoes), 3),
        "desvio_do_periodo_amostras_max": round(float(np.max(np.abs(desvio))), 2),
        "tempo_reamostragem_s": round(t_reamostragem, 1),
        "tempo_receptor_s": round(t_receptor, 1),
        "tempo_por_segundo_de_captura_s": round(t_receptor / duracao, 2),
        "versao_do_codigo": versao_do_codigo(),
    }
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    saida = RAIZ / "dados" / "logs" / f"receptor_captura_real_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

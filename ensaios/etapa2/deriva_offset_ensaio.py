"""Ensaio de deriva do offset residual: mede a portadora da OOK e a temperatura do Pluto ao longo do tempo.

Deve rodar enquanto o pluto_tx_ook_v2_ensaio.py transmite. A cada iteração lê a
temperatura do AD9364 (sensor interno, via libiio, sem mexer no TX) e captura
0,5 s no RTL com a leitura contínua do projeto; o offset vem da raia da portadora.
Grava um JSON em dados/logs/.

Uso: python ensaios/etapa2/deriva_offset_ensaio.py <duracao_s>
"""

import json
import sys
import time
from pathlib import Path

import iio
from decodificar_quadros_ensaio import offset_residual_hz

from sdrlink.hw.rtl_rx import AMOSTRAS_POR_LEITURA, ConfigRtl, capturar
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]


def temperatura_pluto_c(sensor):
    return int(sensor.attrs["input"].value) / 1000


def main():
    duracao_s = float(sys.argv[1])
    sensor = iio.Context("ip:192.168.2.22").find_device("ad9361-phy").find_channel("temp0")
    config = ConfigRtl(915e6, 2.048e6, 10.0)
    inicio = time.time()
    pontos = []
    for _ in range(1000):  # limite fixo (regra 2); sai pelo tempo
        t = time.time() - inicio
        if t > duracao_s:
            break
        temp = temperatura_pluto_c(sensor)
        cap = capturar(config, 4 * AMOSTRAS_POR_LEITURA)
        off = float(offset_residual_hz(cap.amostras.astype(complex)))
        pontos.append({"t_s": round(t, 2), "offset_hz": round(off, 1), "temp_pluto_c": temp})
        print(f"t={t:6.1f} s  offset={off:+8.1f} Hz  T_pluto={temp:.1f} °C", flush=True)
    saida = RAIZ / "dados" / "logs" / f"deriva_offset_{carimbo_de_tempo()}.json"
    registro = {
        "ensaio": "deriva do offset residual da OOK de referência durante a transmissão",
        "versao_do_codigo": versao_do_codigo(),
        "rtl": {"centro_hz": cap.centro_hz, "taxa_sps": cap.taxa_sps, "ganho_db": cap.ganho_db, "correcao_ppm": cap.correcao_ppm},
        "pontos": pontos,
    }
    saida.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    main()

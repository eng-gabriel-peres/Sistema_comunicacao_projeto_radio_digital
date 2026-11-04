"""Figura do offset residual ao longo do tempo (ensaio de deriva e capturas da Etapa 2).

Uso: python ensaios/etapa2/figura_deriva_ensaio.py <deriva.json> <saida.png>
"""

import glob
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from decodificar_quadros_ensaio import offset_residual_hz

RAIZ = Path(__file__).resolve().parents[2]


def main():
    reg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    t = np.array([p["t_s"] for p in reg["pontos"]])
    off = np.array([p["offset_hz"] for p in reg["pontos"]])
    temp = np.array([p["temp_pluto_c"] for p in reg["pontos"]])
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7.5))
    a1.plot(t, off, "o-", ms=3, label="offset residual (RTL, 0,5 s por ponto)")
    a1.set_xlabel("tempo desde o início da transmissão (s)")
    a1.set_ylabel("offset (Hz)")
    a1.grid(alpha=0.3)
    b = a1.twinx()
    b.step(t, temp, "r-", where="mid", alpha=0.6, label="temperatura do AD9364 (°C)")
    b.set_ylim(30, 40)
    b.set_ylabel("°C", color="r")
    a1.set_title(f"Uma transmissão de 60 s (10:42): offset de {off.min():+.0f} a {off.max():+.0f} Hz; temperatura do Pluto parada")
    a1.legend(loc="upper right")
    b.legend(loc="lower left")
    horas, valores = [], []
    for f in sorted(glob.glob(str(RAIZ / "dados" / "capturas" / "ook_ref_*.npy"))):
        carimbo = re.search(r"(\d{8}_\d{6})$", Path(f).stem)
        if carimbo:
            horas.append(datetime.strptime(carimbo.group(1), "%Y%m%d_%H%M%S"))
        else:  # sem horário no nome: usa a hora em que o arquivo foi gravado
            horas.append(datetime.fromtimestamp(Path(f).stat().st_mtime))
        valores.append(offset_residual_hz(np.load(f).astype(np.complex128)))
    cal = [(datetime(2026, 11, 4, 10, 6, 31), -356.0), (datetime(2026, 11, 4, 10, 9, 17), -524.0)]
    a2.plot([h for h, _ in cal], [v for _, v in cal], "s", ms=8, label="calibração com tom (915,25 MHz)")
    a2.plot(horas, valores, "o", label="capturas da OOK (915,2 MHz)")
    a2.set_ylabel("offset (Hz)")
    a2.set_title("Offset residual ao longo da manhã de 04/11, com +84 ppm aplicados")
    a2.grid(alpha=0.3)
    a2.legend()
    a2.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    fig.tight_layout()
    fig.savefig(sys.argv[2], dpi=100)


if __name__ == "__main__":
    main()

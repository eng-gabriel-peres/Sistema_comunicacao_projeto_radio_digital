"""Mede o erro ABSOLUTO do RTL-SDR com emissoras FM (não depende do Pluto).

Uso:
    python scripts/verificar_ppm_fm.py --estacoes 101.7e6 107.3e6 95.1e6

Por padrão a captura usa a correção de configs/rtl.toml; o erro absoluto do
RTL é o erro medido menos a correção aplicada. Cada emissora tem tolerância
própria (alguns ppm), então vale usar duas ou mais e olhar a mediana.
Grava o resultado em dados/calibracao/fm_<data>.json.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from sdrlink.calibracao import PPM
from sdrlink.config import correcao_rtl_ppm_padrao
from sdrlink.fm import desvio_portadora_fm, erro_absoluto_ppm
from sdrlink.hw.rtl_rx import AMOSTRAS_POR_LEITURA, ConfigRtl, capturar
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo

DESLOCAMENTO_HZ = 250e3  # emissora fica longe do pico DC do RTL
LEITURAS_POR_ESTACAO = 32  # 32 x 256 k amostras = 4,1 s a 2,048 MS/s


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--estacoes", type=float, nargs="+", default=[101.7e6, 107.3e6, 95.1e6])
    p.add_argument("--taxa-sps", type=float, default=2.048e6)
    p.add_argument("--ganho-db", type=float, default=20.0)
    p.add_argument(
        "--correcao-ppm",
        type=int,
        default=correcao_rtl_ppm_padrao(),
        help="correção aplicada durante a medida (padrão: configs/rtl.toml)",
    )
    return p.parse_args()


def _medir_estacao(estacao_hz: float, args: argparse.Namespace) -> dict[str, float]:
    """Captura uma emissora e devolve o desvio medido e o erro absoluto do RTL."""
    config = ConfigRtl(
        estacao_hz - DESLOCAMENTO_HZ, args.taxa_sps, args.ganho_db, args.correcao_ppm
    )
    try:
        captura = capturar(config, LEITURAS_POR_ESTACAO * AMOSTRAS_POR_LEITURA)
    except RuntimeError as erro:
        raise SystemExit(f"Erro: {erro}") from erro
    desvio_hz, incerteza_hz = desvio_portadora_fm(
        captura.amostras, captura.taxa_sps, DESLOCAMENTO_HZ
    )
    ppm_medido = desvio_hz / estacao_hz * PPM
    ppm_absoluto = erro_absoluto_ppm(ppm_medido, captura.correcao_ppm)
    print(
        f"FM {estacao_hz / 1e6:6.1f} MHz: {desvio_hz:+8.1f} Hz (±{incerteza_hz:.0f} Hz) = "
        f"{ppm_medido:+7.2f} ppm com {captura.correcao_ppm:+d} ppm -> RTL {ppm_absoluto:+7.2f} ppm"
    )
    return {
        "estacao_hz": estacao_hz,
        "desvio_hz": desvio_hz,
        "incerteza_hz": incerteza_hz,
        "ppm_medido": ppm_medido,
        "ppm": ppm_absoluto,
    }


def main() -> int:
    """Mede cada emissora e resume o erro absoluto do receptor em ppm."""
    args = _argumentos()
    medidas = [_medir_estacao(estacao_hz, args) for estacao_hz in args.estacoes]
    mediana = float(np.median([m["ppm"] for m in medidas]))
    print(
        f"\nErro absoluto do RTL (mediana): {mediana:+.1f} ppm -> "
        f"correção absoluta ~ {round(-mediana):+d} ppm"
    )
    caminho = RAIZ / "dados" / "calibracao" / f"fm_{carimbo_de_tempo()}.json"
    registro: dict[str, object] = {
        "versao_codigo": versao_do_codigo(),
        "parametros": vars(args),
        "medidas": medidas,
        "erro_mediano_ppm": mediana,
    }
    print(f"Registro: {salvar_json(caminho, registro)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

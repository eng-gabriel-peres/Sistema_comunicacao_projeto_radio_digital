"""Calibra a frequência do RTL-SDR com o sinal do Pluto (tom puro ou OOK de referência).

Funciona com o tom do `tx_test.py` e com a OOK do `pluto_tx_ook_v2.py`: nos dois
casos a componente mais forte do espectro é a portadora (na OOK a envoltória tem
média positiva e gera uma raia exatamente na portadora).

Procedimento (requisitos CAL-01 e CAL-02):
    1. captura SEM correção e mede onde a portadora chegou (erro em ppm);
    2. calcula a correção inteira da librtlsdr e o resíduo previsto;
    3. captura COM a correção e mede o resíduo de verdade;
    4. grava o registro em dados/calibracao/ (JSON e figura).

Uso (RTL-SDR ligado há pelo menos 10 min, Pluto transmitindo):
    python scripts/calibrar_rtl.py --freq-tom-hz 915.2e6 --minutos-ligado 15
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

import numpy as np
from matplotlib.figure import Figure

from sdrlink.calibracao import (
    JANELA_FINA_HZ,
    MARGEM_AMBIGUIDADE_DB,
    N_FFT_PADRAO,
    SNR_MINIMA_DB,
    Estatistica,
    Raia,
    correcao_rtl_ppm,
    detectar_raias,
    erro_ppm,
    espectro_medio,
    estimar_por_blocos,
    residuo_previsto_hz,
    resumir,
)
from sdrlink.hw.rtl_rx import Captura, ConfigRtl, capturar, fracao_saturada
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo

PASTA_SAIDA = RAIZ / "dados" / "calibracao"
SATURACAO_MAXIMA = 1e-3
AQUECIMENTO_MIN = 10
MEIA_LARGURA_FIGURA_HZ = 2e3
MEDIDAS_MAX = 64  # 64 blocos de 2^20 amostras = 512 MB em complex64


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "--freq-tom-hz", type=float, required=True, help="frequência RF do tom/portadora"
    )
    p.add_argument(
        "--deslocamento-hz", type=float, default=250e3, help="tom fica nesta freq. em banda base"
    )
    p.add_argument("--taxa-sps", type=float, default=2.048e6, help="taxa de amostragem do RTL")
    p.add_argument("--ganho-db", type=float, default=40.0, help="ganho manual (AGC desligado)")
    p.add_argument("--medidas", type=int, default=8, help="blocos de 2^20 amostras por captura")
    p.add_argument("--janela-busca-hz", type=float, default=60e3, help="meia largura da busca")
    p.add_argument(
        "--minutos-ligado", type=float, default=None, help="há quanto tempo o RTL está ligado"
    )
    p.add_argument("--salvar-iq", action="store_true", help="grava a captura sem correção (.npy)")
    args = p.parse_args()
    if not 1 <= args.medidas <= MEDIDAS_MAX:
        p.error(f"--medidas deve ficar entre 1 e {MEDIDAS_MAX}")
    return args


def _escolher_raia(raias: list[Raia]) -> Raia:
    """Mostra as raias candidatas e escolhe a mais forte, se não houver ambiguidade."""
    for raia in raias:
        print(f"  raia em {raia.freq_hz / 1e3:+10.3f} kHz (banda base): {raia.snr_db:5.1f} dB")
    if not raias or raias[0].snr_db < SNR_MINIMA_DB:
        raise SystemExit(
            f"Portadora não encontrada (nenhuma raia {SNR_MINIMA_DB:.0f} dB acima do ruído). "
            "Confira a frequência, se o Pluto está transmitindo e o ganho."
        )
    if len(raias) > 1 and raias[0].snr_db - raias[1].snr_db < MARGEM_AMBIGUIDADE_DB:
        raise SystemExit(
            "Ambíguo: duas raias com menos de "
            f"{MARGEM_AMBIGUIDADE_DB:.0f} dB de diferença. Reduza --janela-busca-hz, "
            "aumente o ganho ou peça mais potência no Pluto."
        )
    return raias[0]


def _medir(config: ConfigRtl, args: argparse.Namespace) -> tuple[Captura, Estatistica]:
    """Captura, confere saturação, detecta a portadora no espectro médio e mede por bloco."""
    try:
        captura = capturar(config, args.medidas * N_FFT_PADRAO)
    except RuntimeError as erro:
        raise SystemExit(f"Erro: {erro}") from erro
    saturada = fracao_saturada(captura.amostras)
    if saturada > SATURACAO_MAXIMA:
        print(f"  AVISO: {saturada:.2%} das amostras saturadas; reduza --ganho-db")
    freqs, potencia = espectro_medio(captura.amostras, captura.taxa_sps)
    raia = _escolher_raia(
        detectar_raias(freqs, potencia, args.deslocamento_hz, args.janela_busca_hz)
    )
    estimativas = estimar_por_blocos(
        captura.amostras, captura.taxa_sps, raia.freq_hz, JANELA_FINA_HZ
    )
    return captura, resumir(estimativas, N_FFT_PADRAO / captura.taxa_sps)


def _espectro_db(captura: Captura, freq_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Espectro (dB, normalizado) do 1º bloco, ±2 kHz em torno de freq_hz."""
    bloco = captura.amostras[:N_FFT_PADRAO].astype(np.complex128)
    potencia = np.abs(np.fft.fft((bloco - bloco.mean()) * np.hanning(N_FFT_PADRAO))) ** 2
    freqs = np.fft.fftfreq(N_FFT_PADRAO, 1 / captura.taxa_sps)
    janela = np.abs(freqs - freq_hz) <= MEIA_LARGURA_FIGURA_HZ
    ordem = np.argsort(freqs[janela])
    db = 10 * np.log10(potencia[janela][ordem] / potencia[janela].max())
    return freqs[janela][ordem] - freq_hz, db


def _figura(antes: Captura, depois: Captura, resultado: dict[str, float], caminho: str) -> None:
    """Salva o espectro em torno da portadora, antes e depois da correção."""
    fig = Figure(figsize=(10, 4.5))
    ax = fig.subplots()
    for captura, nome, chave in (
        (antes, "sem correção", "offset_antes_hz"),
        (depois, "com correção", "residuo_medido_hz"),
    ):
        f, db = _espectro_db(captura, resultado["deslocamento_hz"])
        linha = ax.plot(f, db, lw=0.8, label=f"{nome} ({captura.correcao_ppm} ppm)")[0]
        ax.axvline(resultado[chave], color=linha.get_color(), ls="--", lw=0.8)
    ax.axvline(0, color="k", lw=0.8, label="frequência esperada")
    ax.set_xlabel("Desvio em relação à frequência esperada (Hz)")
    ax.set_ylabel("Potência relativa (dB)")
    ax.set_ylim(-80, 3)
    ax.set_title(
        f"Calibração do RTL-SDR: erro {resultado['erro_ppm']:+.2f} ppm, "
        f"resíduo {resultado['residuo_medido_hz']:+.0f} Hz"
    )
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(caminho, dpi=110)


def _calcular(freq_tom_hz: float, antes: Captura, est_antes: Estatistica) -> dict[str, float]:
    """Erro em ppm, correção inteira e resíduo previsto a partir da captura sem correção."""
    freq_medida_hz = antes.centro_hz + est_antes.media_hz
    erro = erro_ppm(freq_medida_hz, freq_tom_hz)
    correcao = correcao_rtl_ppm(erro)
    return {
        "freq_medida_hz": freq_medida_hz,
        "offset_antes_hz": freq_medida_hz - freq_tom_hz,
        "erro_ppm": erro,
        "correcao_ppm": float(correcao),
        "residuo_previsto_hz": residuo_previsto_hz(erro, correcao, freq_tom_hz),
    }


def _relatorio(
    resultado: dict[str, float], est_antes: Estatistica, est_depois: Estatistica
) -> None:
    """Imprime o resumo da calibração."""
    print("\n=== Calibração ===")
    print(
        f"Offset sem correção : {resultado['offset_antes_hz']:+9.1f} Hz "
        f"({resultado['erro_ppm']:+.3f} ppm), desvio {est_antes.desvio_hz:.2f} Hz, "
        f"deriva {est_antes.deriva_hz_s:+.2f} Hz/s, SNR mín. {est_antes.snr_min_db:.1f} dB"
    )
    print(
        f"Correção aplicada   : {resultado['correcao_ppm']:+.0f} ppm (librtlsdr só aceita inteiro)"
    )
    print(f"Resíduo previsto    : {resultado['residuo_previsto_hz']:+9.1f} Hz")
    print(
        f"Resíduo medido      : {resultado['residuo_medido_hz']:+9.1f} Hz, "
        f"desvio {est_depois.desvio_hz:.2f} Hz, SNR mín. {est_depois.snr_min_db:.1f} dB"
    )
    piorou = abs(resultado["residuo_medido_hz"]) > abs(resultado["offset_antes_hz"])
    if piorou and resultado["correcao_ppm"] != 0:
        print("AVISO: o resíduo ficou MAIOR que o offset original; conferir o sinal da correção.")


def main() -> int:
    """Executa a calibração completa e grava o registro."""
    args = _argumentos()
    if args.minutos_ligado is None or args.minutos_ligado < AQUECIMENTO_MIN:
        print(
            f"Lembrete: aguarde {AQUECIMENTO_MIN} min com o RTL ligado antes de calibrar (PLT-06)."
        )
    centro_hz = args.freq_tom_hz - args.deslocamento_hz
    print(
        f"1/2 Capturando SEM correção: centro {centro_hz / 1e6:.4f} MHz, ganho {args.ganho_db} dB"
    )
    antes, est_antes = _medir(ConfigRtl(centro_hz, args.taxa_sps, args.ganho_db, 0), args)
    resultado = _calcular(args.freq_tom_hz, antes, est_antes)
    print(f"2/2 Capturando COM correção de {resultado['correcao_ppm']:+.0f} ppm")
    config = ConfigRtl(centro_hz, args.taxa_sps, args.ganho_db, int(resultado["correcao_ppm"]))
    depois, est_depois = _medir(config, args)
    resultado["residuo_medido_hz"] = depois.centro_hz + est_depois.media_hz - args.freq_tom_hz
    resultado["deslocamento_hz"] = args.deslocamento_hz
    _relatorio(resultado, est_antes, est_depois)
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    base = PASTA_SAIDA / f"calibracao_{carimbo_de_tempo()}"
    _figura(antes, depois, resultado, str(base.with_suffix(".png")))
    registro: dict[str, object] = {
        "versao_codigo": versao_do_codigo(),
        "parametros": vars(args),
        "rtl_ganho_lido_db": antes.ganho_db,
        "taxa_lida_sps": antes.taxa_sps,
        "resultado": resultado,
        "estatistica_sem_correcao": asdict(est_antes),
        "estatistica_com_correcao": asdict(est_depois),
    }
    print(f"\nRegistro: {salvar_json(base.with_suffix('.json'), registro)}")
    if args.salvar_iq:
        np.save(base.with_suffix(".npy"), antes.amostras)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Calibra a frequência do RTL-SDR com o sinal do Pluto (tom do tx_test.py ou OOK).

Procedimento (requisitos CAL-01 e CAL-02):
    1. captura com a correção inicial (padrão 0) e acha a portadora no espectro
       médio, descartando raias na grade de espúrios internos do RTL;
    2. calcula a correção total (inicial + correção do que sobrou, achado A5);
    3. captura com a correção total e mede o resíduo de verdade;
    4. grava o registro em dados/calibracao/ (JSON e figura).

Com --tx-test, a frequência esperada é a da raia principal do tx_test.py
(LO + 199,219 kHz), e não LO + 200 kHz: o tom não fecha ciclos inteiros no
buffer cíclico de 1024 amostras (achado A15).

Uso:
    ao vivo (tx_test.py): python scripts/calibrar_rtl.py --freq-tom-hz 915.2e6 --tx-test
                          --correcao-inicial-ppm 1 (padrão: configs/rtl.toml)
    ao vivo (OOK v2)    : python scripts/calibrar_rtl.py --freq-tom-hz 915.2e6
    gravado             : acrescentar --arquivo-iq captura.npy (mesma sintonia e correção)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from sdrlink.calibracao import (
    JANELA_FINA_HZ,
    MARGEM_AMBIGUIDADE_DB,
    N_FFT_PADRAO,
    SNR_MINIMA_DB,
    Estatistica,
    Raia,
    correcao_total_ppm,
    detectar_raias,
    erro_ppm,
    espectro_medio,
    estimar_por_blocos,
    mesmo_pente,
    possivel_espurio_rtl,
    raia_principal_tx_test,
    residuo_previsto_hz,
    resumir,
)
from sdrlink.config import correcao_rtl_ppm_padrao
from sdrlink.hw.rtl_rx import Captura, ConfigRtl, capturar, fracao_saturada
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo

PASTA_SAIDA = RAIZ / "dados" / "calibracao"
SATURACAO_MAXIMA = 1e-3
AQUECIMENTO_MIN = 10
MEIA_LARGURA_FIGURA_HZ = 4e3
MEDIDAS_MAX = 64  # 64 blocos de 2^20 amostras = 512 MB em complex64
N_CANDIDATAS = 6
TX_TEST_TOM_HZ = 200e3  # constantes de referencia/tx_test.py
TX_TEST_TAXA_SPS = 2e6
TX_TEST_BUFFER = 1024


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--freq-tom-hz", type=float, required=True, help="frequência nominal do tom")
    p.add_argument("--tx-test", action="store_true", help="tom gerado pelo tx_test.py (achado A15)")
    p.add_argument(
        "--correcao-inicial-ppm",
        type=int,
        default=correcao_rtl_ppm_padrao(),
        help="correção da 1ª captura (padrão: configs/rtl.toml)",
    )
    p.add_argument("--deslocamento-hz", type=float, default=250e3, help="tom em banda base")
    p.add_argument("--taxa-sps", type=float, default=2.048e6, help="taxa de amostragem do RTL")
    p.add_argument("--ganho-db", type=float, default=40.0, help="ganho manual (AGC desligado)")
    p.add_argument("--medidas", type=int, default=8, help="blocos de 2^20 amostras por captura")
    p.add_argument("--janela-busca-hz", type=float, default=150e3, help="meia largura da busca")
    p.add_argument("--minutos-ligado", type=float, default=None, help="tempo do RTL ligado")
    p.add_argument("--arquivo-iq", type=Path, default=None, help="analisa captura gravada (.npy)")
    p.add_argument("--aceitar-espurios", action="store_true", help="não descarta a grade do RTL")
    p.add_argument("--salvar-iq", action="store_true", help="grava as capturas (.npy)")
    args = p.parse_args()
    if not 1 <= args.medidas <= MEDIDAS_MAX:
        p.error(f"--medidas deve ficar entre 1 e {MEDIDAS_MAX}")
    return args


def _freq_esperada(args: argparse.Namespace) -> float:
    """Frequência RF onde o tom realmente está."""
    if not args.tx_test:
        return float(args.freq_tom_hz)
    lo_hz = args.freq_tom_hz - TX_TEST_TOM_HZ
    return raia_principal_tx_test(lo_hz, TX_TEST_TOM_HZ, TX_TEST_TAXA_SPS, TX_TEST_BUFFER)


def _obter_captura(config: ConfigRtl, args: argparse.Namespace) -> Captura:
    """Captura no rádio ou lê uma captura gravada com os mesmos parâmetros."""
    if args.arquivo_iq is None:
        try:
            return capturar(config, args.medidas * N_FFT_PADRAO)
        except RuntimeError as erro:
            raise SystemExit(f"Erro: {erro}") from erro
    amostras = np.load(args.arquivo_iq)
    if amostras.ndim != 1 or not np.iscomplexobj(amostras):
        raise SystemExit(f"Erro: {args.arquivo_iq} não é um vetor IQ complexo 1-D")
    return Captura(
        amostras.astype(np.complex64),
        config.centro_hz,
        config.taxa_sps,
        config.ganho_db,
        config.correcao_ppm,
    )


def _escolher_raia(raias: list[Raia], captura: Captura, args: argparse.Namespace) -> Raia:
    """Mostra as candidatas, descarta espúrios do RTL e escolhe sem ambiguidade.

    No modo --tx-test, os dentes vizinhos do pente do tx_test.py são do mesmo
    sinal e não contam como raia concorrente.
    """
    aceitar_espurios = bool(args.aceitar_espurios)
    validas: list[Raia] = []
    for raia in raias:
        rf_hz = captura.centro_hz + raia.freq_hz
        espurio = possivel_espurio_rtl(rf_hz, captura.taxa_sps, captura.correcao_ppm)
        descartada = espurio and not aceitar_espurios
        marca = "  <- grade de espúrios do RTL, descartada" if descartada else ""
        print(f"  raia em {rf_hz / 1e6:.6f} MHz: {raia.snr_db:5.1f} dB{marca}")
        if not descartada:
            validas.append(raia)
    if not validas or validas[0].snr_db < SNR_MINIMA_DB:
        raise SystemExit(
            f"Portadora não encontrada (nenhuma raia válida {SNR_MINIMA_DB:.0f} dB acima do "
            "ruído). Confira a frequência, se o Pluto está transmitindo e o ganho."
        )
    passo_hz = TX_TEST_TAXA_SPS / TX_TEST_BUFFER
    concorrentes = [
        r
        for r in validas[1:]
        if not (args.tx_test and mesmo_pente(r.freq_hz, validas[0].freq_hz, passo_hz))
    ]
    if concorrentes and validas[0].snr_db - concorrentes[0].snr_db < MARGEM_AMBIGUIDADE_DB:
        raise SystemExit(
            f"Ambíguo: duas raias com menos de {MARGEM_AMBIGUIDADE_DB:.0f} dB de diferença. "
            "Reduza --janela-busca-hz ou peça mais potência no Pluto."
        )
    return validas[0]


def _medir(
    config: ConfigRtl, args: argparse.Namespace, esperada_hz: float
) -> tuple[Captura, Estatistica]:
    """Obtém a captura, detecta a portadora no espectro médio e mede bloco a bloco."""
    captura = _obter_captura(config, args)
    saturada = fracao_saturada(captura.amostras)
    if saturada > SATURACAO_MAXIMA:
        print(f"  AVISO: {saturada:.2%} das amostras saturadas; reduza --ganho-db")
    freqs, potencia = espectro_medio(captura.amostras, captura.taxa_sps)
    busca_hz = esperada_hz - captura.centro_hz
    raias = detectar_raias(freqs, potencia, busca_hz, args.janela_busca_hz, N_CANDIDATAS)
    raia = _escolher_raia(raias, captura, args)
    estimativas = estimar_por_blocos(
        captura.amostras, captura.taxa_sps, raia.freq_hz, JANELA_FINA_HZ
    )
    return captura, resumir(estimativas, N_FFT_PADRAO / captura.taxa_sps)


def _calcular(esperada_hz: float, antes: Captura, est: Estatistica) -> dict[str, float]:
    """Erro com a correção inicial, correção total e resíduo previsto."""
    freq_medida_hz = antes.centro_hz + est.media_hz
    erro = erro_ppm(freq_medida_hz, esperada_hz)
    total = correcao_total_ppm(antes.correcao_ppm, erro)
    return {
        "freq_esperada_hz": esperada_hz,
        "freq_medida_hz": freq_medida_hz,
        "offset_antes_hz": freq_medida_hz - esperada_hz,
        "correcao_inicial_ppm": float(antes.correcao_ppm),
        "erro_com_correcao_inicial_ppm": erro,
        "erro_total_ppm": erro - antes.correcao_ppm,
        "correcao_ppm": float(total),
        "residuo_previsto_hz": residuo_previsto_hz(erro, total - antes.correcao_ppm, esperada_hz),
    }


def _espectro_db(captura: Captura, centro_rf_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Espectro médio (dB, normalizado) ±4 kHz em torno de centro_rf_hz."""
    freqs, potencia = espectro_medio(captura.amostras, captura.taxa_sps)
    rf = captura.centro_hz + freqs
    janela = np.abs(rf - centro_rf_hz) <= MEIA_LARGURA_FIGURA_HZ
    ordem = np.argsort(rf[janela])
    db = 10 * np.log10(potencia[janela][ordem] / float(np.max(potencia[janela])))
    return rf[janela][ordem] - centro_rf_hz, db


def _figura(
    antes: Captura, depois: Captura | None, resultado: dict[str, float], caminho: Path
) -> None:
    """Salva o espectro em torno da frequência esperada, antes e depois da correção."""
    fig = Figure(figsize=(10, 4.5))
    ax = fig.subplots()
    pares = [(antes, "offset_antes_hz")]
    if depois is not None:
        pares.append((depois, "residuo_medido_hz"))
    for captura, chave in pares:
        f, db = _espectro_db(captura, resultado["freq_esperada_hz"])
        linha = ax.plot(f, db, lw=0.8, label=f"correção {captura.correcao_ppm:+d} ppm")[0]
        if abs(resultado[chave]) <= MEIA_LARGURA_FIGURA_HZ:
            ax.axvline(resultado[chave], color=linha.get_color(), ls="--", lw=0.8)
    ax.axvline(0, color="k", lw=0.8, label="frequência esperada")
    ax.set_xlabel("Desvio em relação à frequência esperada (Hz)")
    ax.set_ylabel("Potência relativa (dB)")
    ax.set_ylim(-60, 3)
    ax.set_title(f"Calibração do RTL-SDR: correção {resultado['correcao_ppm']:+.0f} ppm")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(caminho, dpi=110)


def _relatorio(resultado: dict[str, float], est_antes: Estatistica) -> None:
    """Imprime o resumo da calibração."""
    print("\n=== Calibração ===")
    print(f"Esperada         : {resultado['freq_esperada_hz'] / 1e6:.6f} MHz")
    print(
        f"Medida           : {resultado['freq_medida_hz'] / 1e6:.6f} MHz com "
        f"{resultado['correcao_inicial_ppm']:+.0f} ppm (desvio {est_antes.desvio_hz:.0f} Hz, "
        f"SNR mín. {est_antes.snr_min_db:.1f} dB)"
    )
    print(f"Erro total       : {resultado['erro_total_ppm']:+.2f} ppm")
    print(f"Correção total   : {resultado['correcao_ppm']:+.0f} ppm")
    print(f"Resíduo previsto : {resultado['residuo_previsto_hz']:+.0f} Hz")
    if "residuo_medido_hz" in resultado:
        print(f"Resíduo medido   : {resultado['residuo_medido_hz']:+.0f} Hz")


def _registrar(
    args: argparse.Namespace,
    resultado: dict[str, float],
    estatisticas: tuple[Estatistica, Estatistica | None],
    base: Path,
) -> Path:
    """Grava o JSON do ensaio."""
    est_antes, est_depois = estatisticas
    registro: dict[str, object] = {
        "versao_codigo": versao_do_codigo(),
        "parametros": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "resultado": resultado,
        "estatistica_antes": asdict(est_antes),
        "estatistica_depois": asdict(est_depois) if est_depois else None,
    }
    return salvar_json(base.with_suffix(".json"), registro)


def main() -> int:
    """Executa a calibração completa e grava o registro."""
    args = _argumentos()
    if args.arquivo_iq is None and (args.minutos_ligado or 0) < AQUECIMENTO_MIN:
        print(f"Lembrete: aguarde {AQUECIMENTO_MIN} min com o RTL ligado (PLT-06).")
    esperada_hz = _freq_esperada(args)
    centro_hz = args.freq_tom_hz - args.deslocamento_hz  # mesma sintonia das capturas gravadas
    config = ConfigRtl(centro_hz, args.taxa_sps, args.ganho_db, args.correcao_inicial_ppm)
    print(f"1/2 Captura com {config.correcao_ppm:+d} ppm: esperado {esperada_hz / 1e6:.6f} MHz")
    antes, est_antes = _medir(config, args, esperada_hz)
    resultado = _calcular(esperada_hz, antes, est_antes)
    depois: Captura | None = None
    est_depois: Estatistica | None = None
    if args.arquivo_iq is None:
        total = int(resultado["correcao_ppm"])
        print(f"2/2 Captura com a correção total de {total:+d} ppm")
        config_total = ConfigRtl(centro_hz, args.taxa_sps, args.ganho_db, total)
        depois, est_depois = _medir(config_total, args, esperada_hz)
        resultado["residuo_medido_hz"] = depois.centro_hz + est_depois.media_hz - esperada_hz
    _relatorio(resultado, est_antes)
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    base = PASTA_SAIDA / f"calibracao_{carimbo_de_tempo()}"
    _figura(antes, depois, resultado, base.with_suffix(".png"))
    print(f"\nRegistro: {_registrar(args, resultado, (est_antes, est_depois), base)}")
    if args.salvar_iq and args.arquivo_iq is None:
        np.save(base.with_name(base.name + "_antes.npy"), antes.amostras)
        if depois is not None:
            np.save(base.with_name(base.name + "_depois.npy"), depois.amostras)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Mede o ruído de fase do par Pluto + RTL num tom gravado e compara com o que cada perfil aguenta.

Na bancada (sessão 1 do plano de bancada), com o RTL aquecido 10 minutos:
    TX:  python scripts/transmitir_tom.py --freq-tom-hz 919.75e6 --duracao-s 30
    RX:  python scripts/gravar_iq.py --centro-hz 919.5e6 --segundos 4 --nome tom
    RX:  python scripts/medir_ruido_de_fase.py dados/capturas/tom_<carimbo>.npy

Para cada perfil final mostra a variação de fase em um símbolo (a que os receptores
diferenciais veem), com a parte do ruído branco da gravação descontada, e a compara
com a tolerância medida em simulação (docs/etapa6_imperfeicoes.md). Grava
<captura>_ruido_de_fase.json ao lado da captura.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import config, fase
from sdrlink.registro import salvar_json, versao_do_codigo

PERFIS_FINAIS = ("prova-a", "prova-a-24", "prova-a-fec", "prova-a-dbpsk", "prova-b")
AFASTAMENTOS_HZ = (300.0, 1e3, 3e3, 10e3, 30e3, 100e3, 300e3)
AFASTAMENTO_PISO_HZ = 300e3  # longe do tom o espectro é só o ruído branco da gravação
TAXA_PADRAO_SPS = 2.048e6
FRACAO_DA_TOLERANCIA = 0.5  # acima de metade da tolerância: avisar
# variação de fase em um símbolo (rad) com que a PER passa de 1% a 1 dB acima do ponto
# de PER 1%, pela varredura de Wiener do bloco 21 (docs/etapa6_imperfeicoes.md)
TOLERANCIA_RAD: dict[str, float] = {
    "prova-a": 0.0959,  # Wiener de 1 kHz em 3 amostras a 2,048 MS/s
    "prova-a-24": 0.0886,  # 1 kHz em 3 amostras a 2,4 MS/s
    "prova-a-fec": 0.166,  # 3 kHz
    "prova-a-dbpsk": 0.166,  # 3 kHz
    "prova-b": 0.271,  # 300 Hz em 80 amostras
}


def _taxa(captura: Path, taxa_sps: float | None) -> float:
    """A taxa pedida, ou a dos metadados do gravar_iq.py, ou 2,048 MS/s."""
    if taxa_sps is not None:
        return taxa_sps
    metadados = captura.with_suffix(".json")
    if metadados.exists():
        valor = json.loads(metadados.read_text(encoding="utf-8")).get("taxa_sps")
        if isinstance(valor, int | float):
            return float(valor)
    return TAXA_PADRAO_SPS


def _por_perfil(tom: fase.FaseDoTom, piso: float, taxa: float) -> dict[str, dict[str, object]]:
    """Variação de fase em um símbolo de cada perfil final, contra a tolerância."""
    linhas: dict[str, dict[str, object]] = {}
    for nome in PERFIS_FINAIS:
        p = config.perfil(nome)
        atraso = max(1, round(taxa * p.sps / p.taxa_sps))
        medida = fase.variacao_de_fase_rad(tom, atraso)
        branco = fase.variacao_do_ruido_branco_rad(piso, atraso, taxa)
        de_fase = fase.descontar(medida, branco)
        tolerancia = TOLERANCIA_RAD.get(nome)
        situacao = "sem tolerância medida"
        if tolerancia is not None and branco >= FRACAO_DA_TOLERANCIA * tolerancia:
            situacao = "inconclusivo: tom fraco demais (subir o ganho de TX ou de RX)"
        elif tolerancia is not None:
            situacao = "ok" if de_fase < FRACAO_DA_TOLERANCIA * tolerancia else "ATENÇÃO"
        linhas[nome] = {
            "atraso_amostras": atraso,
            "medida_rad": round(medida, 4),
            "ruido_branco_rad": round(branco, 4),
            "ruido_de_fase_rad": round(de_fase, 4),
            "tolerancia_rad": tolerancia,
            "situacao": situacao,
        }
    return linhas


def main() -> int:
    """Lê o tom, mede e grava o registro."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("captura", type=Path, help="gravação do tom (.npy, complex64)")
    p.add_argument("--taxa-sps", type=float, default=None, help="padrão: a dos metadados")
    args = p.parse_args()
    taxa = _taxa(args.captura, args.taxa_sps)
    amostras = np.load(args.captura, mmap_mode="r")
    try:
        tom = fase.fase_do_tom(amostras, taxa)
        l_f = fase.ruido_de_fase_dbc_hz(amostras, taxa, AFASTAMENTOS_HZ)
    except ValueError as erro:
        p.error(str(erro))
    piso = l_f[AFASTAMENTO_PISO_HZ]
    perfis = _por_perfil(tom, piso, taxa)
    registro: dict[str, object] = {
        "captura": args.captura.name,
        "versao_do_codigo": versao_do_codigo(),
        "taxa_sps": taxa,
        "freq_do_tom_hz": round(tom.freq_hz, 1),
        "saltos_de_emenda": tom.saltos,
        "l_dbc_hz": {f"{k:g}": round(v, 1) for k, v in l_f.items()},
        "perfis": perfis,
    }
    caminho = salvar_json(
        args.captura.with_name(args.captura.stem + "_ruido_de_fase.json"), registro
    )
    print(f"Tom em {tom.freq_hz / 1e3:.1f} kHz; piso de {piso:.1f} dBc/Hz")
    print("L(f): " + ", ".join(f"{k / 1e3:g} kHz {v:.1f}" for k, v in l_f.items()) + " dBc/Hz")
    if tom.saltos:
        print(
            f"AVISO: {tom.saltos} saltos de fase (perda de amostras na gravação): trechos excluídos"
        )
    for nome, linha in perfis.items():
        print(
            f"{nome}: {linha['ruido_de_fase_rad']} rad em um símbolo ({linha['atraso_amostras']} "
            f"amostras; medida {linha['medida_rad']}, ruído branco {linha['ruido_branco_rad']}); "
            f"tolerância {linha['tolerancia_rad']}: {linha['situacao']}"
        )
    print(f"Registro: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

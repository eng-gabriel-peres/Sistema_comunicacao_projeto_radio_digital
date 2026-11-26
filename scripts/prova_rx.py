"""RX no dia da prova: grava, decodifica, remonta o arquivo e faz o relatório com gráficos.

Uso (no PC do RX, com o RTL ligado há 10 min):
    python scripts/prova_rx.py --prova a                      (sala: maior goodput)
    python scripts/prova_rx.py --prova b --distancia-m 40     (área externa: uma posição)
    python scripts/prova_rx.py --prova a --captura <arquivo.npy>   (só processa uma gravação)

Passos: grava 70 s (comece quando o TX disser "Sinal pronto"), roda o receber.py (gera
<captura>_saida.txt, o arquivo que o avaliador pede, e <captura>_rx.json), remonta o
arquivo recebido (<captura>_arquivo.bin, na ordem da sequência), e grava na pasta da
prova o relatório <nome>_relatorio.md com a figura <nome>_relatorio.png (espectro com a
banda a 99% e o limite de 1 MHz; pacotes por segundo) e o resumo <nome>_resumo.json, que
o relatorio_alcance.py junta por distância. Sem o log do TX, PER e goodput são estimados
pelos buracos de sequência; com --log-tx, são os exatos do avaliar.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from scipy import signal

from sdrlink import metricas, prova
from sdrlink.registro import salvar_json, versao_do_codigo

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[1]
PERFIS = {"a": "prova-a", "b": "prova-b"}
BANDA_MAX_KHZ = 1000.0
TRECHO_ESPECTRO_S = 4.0


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--prova", choices=sorted(PERFIS), required=True)
    p.add_argument("--perfil", default=None, help="outro perfil (padrão: prova-a ou prova-b)")
    p.add_argument(
        "--ganho-db", type=float, default=25.0, help="ganho do RTL (nível de -20 a -12 dBFS)"
    )
    p.add_argument("--segundos", type=float, default=70.0, help="duração da gravação")
    p.add_argument("--janela-s", type=float, default=60.0, help="janela da prova")
    p.add_argument(
        "--captura", type=Path, default=None, help="processa esta gravação em vez de gravar"
    )
    p.add_argument(
        "--log-tx", type=Path, default=None, help="log do TX (ou a pasta dele), para a PER exata"
    )
    p.add_argument("--distancia-m", type=float, default=None, help="prova B: distância da posição")
    p.add_argument("--posicao", default=None, help="nome da posição (P1, P2...)")
    p.add_argument("--deslocamento-hz", type=float, default=None, help="do escolher_canal.py")
    p.add_argument("--pasta", type=Path, default=None, help="padrão: dados/prova/<data>")
    return p.parse_args()


def _rodar(script: str, *argumentos: str) -> subprocess.CompletedProcess[str]:
    comando = [sys.executable, str(RAIZ / "scripts" / script), *argumentos]
    # o filho escreve em UTF-8 mesmo num PowerShell comum (sem isso, em cp1252, a leitura
    # caía no "Saída" do receber.py; bancada de 25/11)
    ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(  # noqa: S603 (só os scripts do projeto)
        comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, env=ambiente,
    )  # fmt: skip
    print(r.stdout.strip())
    if r.returncode != 0:
        raise SystemExit(f"{script} falhou:\n{r.stderr.strip()[-2000:]}")
    return r


def _gravar(args: argparse.Namespace, perfil: str, pasta: Path, nome: str) -> Path:
    print(f"Gravando {args.segundos:g} s com o perfil {perfil}...", flush=True)
    _rodar(
        "gravar_iq.py", "--perfil", perfil, "--segundos", str(args.segundos),
        "--ganho-db", str(args.ganho_db), "--nome", nome, "--pasta", str(pasta),
    )  # fmt: skip
    return max(pasta.glob(f"{nome}_*.npy"), key=lambda c: c.stat().st_mtime)


def _figura(captura: Path, registro: dict[str, Any], caminho: Path) -> None:
    """Espectro do trecho com sinal (banda a 99% e limite de 1 MHz) e pacotes por segundo."""
    taxa = float(registro["perfil"]["taxa_sps"])
    x = np.load(captura, mmap_mode="r")
    meio = len(x) // 2
    trecho = np.asarray(x[meio : meio + int(TRECHO_ESPECTRO_S * taxa)])
    f, p = signal.welch(trecho, taxa, nperseg=4096, return_onesided=False)
    f, p = np.fft.fftshift(f), np.fft.fftshift(p)
    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(12, 4.2))
    esq.plot(f / 1e3, 10 * np.log10(p), lw=0.8)
    medidas = registro.get("medidas_da_captura") or {}
    limites = medidas.get("banda_99_limites_khz") if isinstance(medidas, dict) else None
    if limites:
        for v in limites:
            esq.axvline(v, color="C1", ls="--", lw=1)
        centro = sum(limites) / 2
        for v in (centro - BANDA_MAX_KHZ / 2, centro + BANDA_MAX_KHZ / 2):
            esq.axvline(v, color="C3", ls=":", lw=1)
        esq.set_title(f"Espectro: banda a 99% de {medidas.get('banda_99_khz')} kHz (limite 1 MHz)")
    esq.set_xlabel("frequência em relação ao LO (kHz)")
    esq.set_ylabel("dB")
    resumo = registro.get("sem_o_log_do_tx") or {}
    por_segundo = resumo.get("pacotes_por_segundo", []) if isinstance(resumo, dict) else []
    dir_.bar(range(len(por_segundo)), por_segundo, width=1.0)
    dir_.set_title("Pacotes aceitos por segundo")
    dir_.set_xlabel("segundos desde o primeiro pacote")
    for ax in (esq, dir_):
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(caminho, dpi=100)
    plt.close(fig)


def _resumo(args: argparse.Namespace, captura: Path, registro: dict[str, Any]) -> dict[str, Any]:
    sem_log = registro.get("sem_o_log_do_tx") or {}
    medidas = registro.get("medidas_da_captura") or {}
    resumo: dict[str, Any] = {
        "prova": args.prova, "perfil": registro["perfil"]["nome"],
        "captura": captura.name, "posicao": args.posicao, "distancia_m": args.distancia_m,
        "pacotes_unicos": sem_log.get("pacotes_unicos", 0),
        "per": sem_log.get("per_estimada"), "goodput_bps": sem_log.get("goodput_estimado_bps", 0.0),
        "per_e_goodput": "estimados pelos buracos de sequência",
        "ebn0_db": medidas.get("ebn0_estimado_db"), "banda_99_khz": medidas.get("banda_99_khz"),
        "offset_hz": registro.get("offset_residual_mediano_hz"),
        "versao_do_codigo": versao_do_codigo(),
    }  # fmt: skip
    if args.log_tx is not None:
        log = args.log_tx
        if log.is_dir():  # TX e RX no mesmo PC: o log mais recente da pasta
            log = max(log.glob("tx_*.txt"), key=lambda c: c.stat().st_mtime)
        _rodar("avaliar.py", str(log), str(captura.with_name(captura.stem + "_saida.txt")),
               "--duracao-s", str(args.janela_s))  # fmt: skip
        av = json.loads(
            captura.with_name(captura.stem + "_saida_avaliacao.json").read_text(encoding="utf-8")
        )
        resumo.update(per=av["per"], goodput_bps=av["goodput_bps"], transmitidos=av["transmitidos"],
                      per_e_goodput="exatos, pelo log do TX")  # fmt: skip
    return resumo


def _relatorio(resumo: dict[str, Any], faltando: int, figura: Path) -> str:
    per = resumo["per"]
    distancia = "-" if resumo["distancia_m"] is None else f"{resumo['distancia_m']:g}"
    versao = resumo["versao_do_codigo"]
    linhas = [
        f"# Prova {str(resumo['prova']).upper()}: {resumo['captura']}",
        "",
        f"Gerado em {datetime.now():%d/%m/%Y %H:%M}, perfil `{resumo['perfil']}`, "
        f"código `{versao}`.",
        "",
        "| Item | Valor |",
        "|---|---|",
        f"| Posição / distância | {resumo['posicao'] or '-'} / {distancia} m |",
        f"| Pacotes únicos recebidos | {resumo['pacotes_unicos']} |",
        f"| Goodput | {resumo['goodput_bps'] / 1e3:.1f} kbit/s ({resumo['per_e_goodput']}) |",
        f"| PER | {100 * float(per):.3f}% |" if per is not None else "| PER | sem dado |",
        f"| Eb/N0 medido | {resumo['ebn0_db']} dB |",
        f"| Banda a 99% | {resumo['banda_99_khz']} kHz (limite 1 000 kHz) |",
        f"| Offset residual | {resumo['offset_hz']} Hz |",
        f"| Arquivo remontado | faltam {faltando} pacotes entre a primeira e a última sequência |",
        f"| Critério da prova A | {prova.criterio_prova_a(per, resumo['banda_99_khz'])} |"
        if resumo["prova"] == "a" else "",
        "",
        f"![espectro e pacotes por segundo]({figura.name})",
        "",
    ]  # fmt: skip
    return "\n".join(linhas)


def main() -> int:
    """Grava (ou usa a captura dada), decodifica, remonta e relata."""
    args = _argumentos()
    perfil = args.perfil or PERFIS[args.prova]
    pasta = args.pasta or RAIZ / "dados" / "prova" / datetime.now().strftime("%Y%m%d")
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"prova_{args.prova}" + (f"_{args.posicao}" if args.posicao else "")
    captura = args.captura or _gravar(args, perfil, pasta, nome)
    extra = ["--deslocamento-hz", str(args.deslocamento_hz)] if args.deslocamento_hz else []
    print("Decodificando...", flush=True)
    _rodar("receber.py", str(captura), "--perfil", perfil, "--janela-s", str(args.janela_s), *extra)
    registro = json.loads(captura.with_name(captura.stem + "_rx.json").read_text(encoding="utf-8"))
    lidos = metricas.ler_pacotes(captura.with_name(captura.stem + "_saida.txt"))
    pacotes, falsos = prova.so_os_da_prova(lidos)
    if falsos:
        print(f"AVISO: {falsos} pacotes com tamanho diferente de 128 bytes (quadros falsos) "
              "ficaram fora do arquivo remontado")  # fmt: skip
    faltando = 0
    if pacotes:
        dados, buracos = prova.remontar(pacotes)
        captura.with_name(captura.stem + "_arquivo.bin").write_bytes(dados)
        faltando = len([b for b in buracos if b >= min(p.sequencia for p in pacotes)])
    resumo = _resumo(args, captura, registro)
    base = pasta / captura.stem
    figura = base.with_name(base.name + "_relatorio.png")
    _figura(captura, registro, figura)
    relatorio = base.with_name(base.name + "_relatorio.md")
    relatorio.write_text(_relatorio(resumo, faltando, figura), encoding="utf-8", newline="\n")
    salvar_json(base.with_name(base.name + "_resumo.json"), resumo)
    goodput = float(resumo["goodput_bps"]) / 1e3
    per = resumo["per"]
    print(
        f"\nRESULTADO: {resumo['pacotes_unicos']} pacotes, goodput {goodput:.1f} kbit/s, "
        f"PER {'?' if per is None else f'{100 * float(per):.3f}%'} ({resumo['per_e_goodput']})"
    )
    if args.prova == "a":
        print(f"Prova A: {prova.criterio_prova_a(per, resumo['banda_99_khz'])}")
    print(f"Relatório: {relatorio}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""TX no dia da prova: um comando transmite o arquivo do professor pelo perfil certo.

Uso (no PC do TX, com o Pluto ligado):
    python scripts/prova_tx.py <arquivo do professor> --prova a
    python scripts/prova_tx.py <arquivo do professor> --prova b --ganho-db -10

Faz o mesmo que o transmitir.py com as escolhas da prova já feitas:
    --prova a  perfil prova-a (DQPSK, cerca de 1 218 kbit/s); --prova b  perfil prova-b
    --pre-gerar sempre (sem ele o TX não acompanha o tempo real: bancada de 25/11)
    contagem regressiva (--atraso-s, padrão 10 s) entre "sinal pronto" e "no ar", para
    o RX começar a gravar e o avaliador dar o início
O arquivo pode ser de qualquer tipo: é fatiado em payloads de 128 bytes (o último é
completado com zeros). Se ele não enche os 60 s, --repetir o repete em ciclo.
O log do TX (e o JSON com o tempo no ar) fica em dados/prova/<data>/.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PERFIS = {"a": "prova-a", "b": "prova-b"}


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("arquivo", type=Path, help="o arquivo que o professor entregou")
    p.add_argument("--prova", choices=sorted(PERFIS), required=True)
    p.add_argument("--perfil", default=None, help="outro perfil (padrão: prova-a ou prova-b)")
    p.add_argument("--ganho-db", type=float, default=-30.0, help="atenuação do Pluto (0 = máximo)")
    p.add_argument("--duracao-s", type=float, default=60.0)
    p.add_argument("--atraso-s", type=float, default=10.0, help="contagem entre pronto e no ar")
    p.add_argument("--deslocamento-hz", type=float, default=None, help="do escolher_canal.py")
    p.add_argument("--repetir", action="store_true", help="repete o arquivo até encher a janela")
    p.add_argument("--pasta", type=Path, default=None, help="padrão: dados/prova/<data>")
    args = p.parse_args()
    if not args.arquivo.exists():
        p.error(f"arquivo não encontrado: {args.arquivo}")
    return args


def main() -> int:
    """Monta e roda o transmitir.py com as escolhas da prova."""
    args = _argumentos()
    perfil = args.perfil or PERFIS[args.prova]
    pasta = args.pasta or RAIZ / "dados" / "prova" / datetime.now().strftime("%Y%m%d")
    pasta.mkdir(parents=True, exist_ok=True)
    comando = [
        sys.executable, str(RAIZ / "scripts" / "transmitir.py"), str(args.arquivo),
        "--perfil", perfil, "--ganho-db", str(args.ganho_db),
        "--duracao-s", str(args.duracao_s), "--pre-gerar",
        "--atraso-s", str(args.atraso_s), "--pasta", str(pasta),
    ]  # fmt: skip
    if args.deslocamento_hz is not None:
        comando += ["--deslocamento-hz", str(args.deslocamento_hz)]
    if args.repetir:
        comando.append("--repetir")
    print(f"Prova {args.prova.upper()}: {perfil}, TX {args.ganho_db:g} dB, {args.duracao_s:g} s")
    print("Gerando o sinal (cerca de 1 min). Grave no RX só no aviso de pronto.", flush=True)
    return subprocess.run(comando, check=False).returncode  # noqa: S603 (só o script do projeto)


if __name__ == "__main__":
    sys.exit(main())

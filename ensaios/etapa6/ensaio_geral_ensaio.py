"""Ensaio geral sem hardware: a prova de 60 s simulada com cada perfil final, com o código final.

Para cada perfil, roda ensaios/etapa6/prova_a_60s_ensaio.py (os comandos da prova:
gerar_payloads.py, transmitir.py --simular, canal com os defeitos medidos do RTL,
receber.py e avaliar.py) num Eb/N0 por bit no ar de 1,5 a 2 dB acima do necessário
para PER de 1% (medido nos blocos 08 a 12), e junta os resultados.

Uso: python ensaios/etapa6/ensaio_geral_ensaio.py
"""

import json
import subprocess
import sys
from pathlib import Path

from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
CASOS = [  # (perfil, Eb/N0 por bit no ar, Eb/N0 necessário para PER 1%, de onde)
    ("prova-a", 14.0, 12.07, "bloco 12, DQPSK com emenda"),
    ("prova-a-fec", 6.0, 4.04, "bloco 10, DQPSK com FEC"),
    ("prova-a-dbpsk", 12.0, 10.36, "bloco 12, DBPSK com emenda"),
    ("prova-b", 6.0, 4.35, "bloco 09, DBPSK com FEC a 25,6 kbit/s"),
]


def main():
    resumo = []
    for perfil, ebn0, necessario, origem in CASOS:
        print(f"== {perfil} a {ebn0} dB", flush=True)
        r = subprocess.run(
            [sys.executable, "ensaios/etapa6/prova_a_60s_ensaio.py", str(ebn0), perfil],
            cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
        )
        if r.returncode != 0:
            raise RuntimeError(f"{perfil} falhou:\n{r.stdout}\n{r.stderr}")
        registro = Path(r.stdout.strip().splitlines()[-1].split("registro: ")[1])
        dados = json.loads(registro.read_text(encoding="utf-8"))
        linha = {
            "perfil": perfil, "ebn0_no_ar_db": ebn0, "ebn0_necessario_db": necessario, "origem": origem,
            "modulacao": dados["perfil"]["modulacao"], "fec": dados["perfil"]["fec"],
            "emendar_caudas": dados["perfil"]["emendar_caudas"],
            "transmitidos": dados["transmitidos"], "recebidos_certos": dados["recebidos_certos"],
            "per": dados["per"], "goodput_kbps": dados["goodput_kbps"],
            "conteudo_diferente": dados["conteudo_diferente"], "espurios": dados["espurios"],
            "banda_99_medida_khz": dados["banda_99_medida_khz"],
            "tempo_rx_processamento_s": dados["tempo_rx_processamento_s"],
            "passa": dados["per"] <= 0.01 and dados["banda_99_medida_khz"] <= 1000
            and dados["tempo_rx_processamento_s"] < 600,
            "registro": registro.name,
        }
        resumo.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "ensaio geral sem hardware: prova de 60 s com cada perfil final",
        "casos": resumo, "todos_passam": all(c["passa"] for c in resumo),
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    print("todos passam:", resultado["todos_passam"])
    saida = RAIZ / "dados" / "logs" / f"ensaio_geral_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())

"""Gera o PDF do relatório de uma entrega a partir dos documentos Markdown de docs/.

Os documentos do repositório são a fonte única: o relatório só os junta na
ordem da entrega, com capa e sumário, e imprime em PDF pelo Edge (ou Chrome)
em modo headless. Assim o PDF nunca diverge do que está versionado.

Uso: python -m ferramentas.gerar_relatorio <entrega>
    entregas: etapas-1-2, etapa-3, etapa-4, etapa-5, etapa-6, final
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import markdown  # type: ignore[import-untyped]

from sdrlink.registro import RAIZ, versao_do_codigo

DOCS = RAIZ / "docs"
NAVEGADORES = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
)
TEMPO_MAX_IMPRESSAO_S = 120

# Parte: (título, arquivo em docs/, título de seção onde começa, título onde termina)
Parte = tuple[str, str, str | None, str | None]


@dataclass(frozen=True)
class Entrega:
    """Uma entrega da disciplina: título da capa, arquivo de saída e partes, em ordem."""

    titulo: str
    arquivo: str
    partes: tuple[Parte, ...]


ENTREGAS = {
    "etapas-1-2": Entrega(
        "Relatório das Etapas 1 e 2",
        "Relatorio_Etapas_1_2_Gabriel_Peres",
        (
            ("Calibração do RTL-SDR (Etapa 1)", "calibracao_rtl.md", None, None),
            (
                "Estudo e auditoria do código de referência (Etapa 2)",
                "00_planejamento_e_auditoria.md",
                "## 4. Auditoria do código de referência",
                "## 6. Matriz de rastreabilidade",
            ),
            (
                "Recepção da OOK de referência no enlace real (Etapa 2)",
                "etapa2_recepcao_ook.md",
                None,
                None,
            ),
            ("Auditoria de conformidade das Etapas 1 e 2", "auditoria_etapas_1_2.md", None, None),
            ("Anexo A: registro de uso de IA", "registro_ia.md", None, "## Etapa 3"),
        ),
    ),
    "etapa-3": Entrega(
        "Relatório da Etapa 3",
        "Relatorio_Etapa_3_Gabriel_Peres",
        (
            ("Quadro v2: número de sequência e CRC-16", "etapa3_quadro.md", None, None),
            ("OOK, 2-FSK e BPSK em simulação", "etapa3_modulacoes.md", None, None),
            ("Receptor multiquadro", "etapa3_receptor.md", None, None),
            ("Transmissor de prova, log do TX e métricas", "etapa3_transmissor.md", None, None),
            ("Anexo A: registro de uso de IA", "registro_ia.md", "## Etapa 3", "## Etapa 4"),
        ),
    ),
    "etapa-4": Entrega(
        "Relatório da Etapa 4",
        "Relatorio_Etapa_4_Gabriel_Peres",
        (
            ("Simulação do canal", "etapa4_canal.md", None, None),
            ("Anexo A: registro de uso de IA", "registro_ia.md", "## Etapa 4", "## Etapa 5"),
        ),
    ),
    "etapa-5": Entrega(
        "Relatório parcial da Etapa 5",
        "Relatorio_Etapa_5_Gabriel_Peres",
        (
            ("Caracterização: ferramentas e protocolo", "etapa5_software.md", None, None),
            ("Anexo A: registro de uso de IA", "registro_ia.md", "## Etapa 5", "## Etapas 6 e 7"),
        ),
    ),
    "final": Entrega(
        "Relatório final: enlace digital Pluto → RTL-SDR",
        "Relatorio_Final_Gabriel_Peres",
        (
            (
                "Síntese: o que funcionou, o que falhou, o que melhorar",
                "relatorio_final.md",
                None,
                None,
            ),
            (
                "Planejamento, requisitos e matriz de rastreabilidade",
                "00_planejamento_e_auditoria.md",
                None,
                None,
            ),
            ("Auditoria de conformidade das Etapas 1 e 2", "auditoria_etapas_1_2.md", None, None),
            ("Etapa 1: calibração do RTL-SDR", "calibracao_rtl.md", None, None),
            (
                "Etapa 2: recepção da OOK de referência no enlace real",
                "etapa2_recepcao_ook.md",
                None,
                None,
            ),
            ("Etapa 3a: quadro com sequência e CRC-16", "etapa3_quadro.md", None, None),
            ("Etapa 3b: OOK, 2-FSK e BPSK em simulação", "etapa3_modulacoes.md", None, None),
            ("Etapa 3c: receptor multiquadro", "etapa3_receptor.md", None, None),
            (
                "Etapa 3d: transmissor de prova, log do TX e métricas",
                "etapa3_transmissor.md",
                None,
                None,
            ),
            ("Etapa 4: simulação do canal", "etapa4_canal.md", None, None),
            ("Etapa 5: caracterização (ferramentas e protocolo)", "etapa5_software.md", None, None),
            ("Etapa 6a: configuração da prova A", "etapa6_prova_a.md", None, None),
            ("Etapa 6b: configuração da prova B", "etapa6_prova_b.md", None, None),
            ("Etapa 6c: FEC para a prova B", "etapa6_fec.md", None, None),
            ("Etapa 6d: DQPSK para a prova A e quadro v3", "etapa6_dqpsk.md", None, None),
            ("Etapa 6e: Viterbi em lote e a reserva com FEC", "etapa6_viterbi_lote.md", None, None),
            ("Etapa 6f: emenda das caudas do RRC", "etapa6_emenda.md", None, None),
            (
                "Etapa 6g: robustez, relógio de amostragem e alimentação do Pluto",
                "etapa6_robustez.md",
                None,
                None,
            ),
            ("Etapa 6h: perfil experimental a 2,4 MS/s", "etapa6_taxa_24.md", None, None),
            ("Roteiro da prova e ensaio geral", "roteiro_da_prova.md", None, None),
            ("Auditoria final de conformidade", "auditoria_final.md", None, None),
            ("Plano de bancada", "plano_de_bancada.md", None, None),
            ("Padrão de código", "padrao_de_codigo.md", None, None),
            ("Anexo A: registro de uso de IA (todas as etapas)", "registro_ia.md", None, None),
        ),
    ),
    "etapa-6": Entrega(
        "Relatório parcial da Etapa 6",
        "Relatorio_Etapa_6_Gabriel_Peres",
        (
            ("Prova A: configuração e perfis", "etapa6_prova_a.md", None, None),
            ("Prova B: configuração de alcance", "etapa6_prova_b.md", None, None),
            ("FEC para a prova B", "etapa6_fec.md", None, None),
            ("DQPSK para a prova A e quadro v3", "etapa6_dqpsk.md", None, None),
            ("Viterbi em lote e a reserva com FEC", "etapa6_viterbi_lote.md", None, None),
            ("Emenda das caudas do RRC", "etapa6_emenda.md", None, None),
            (
                "Robustez: relógio de amostragem e alimentação do Pluto",
                "etapa6_robustez.md",
                None,
                None,
            ),
            ("Perfil experimental a 2,4 MS/s", "etapa6_taxa_24.md", None, None),
            ("Roteiro da prova e ensaio geral", "roteiro_da_prova.md", None, None),
            ("Anexo A: registro de uso de IA", "registro_ia.md", "## Etapas 6 e 7", None),
        ),
    ),
}

IMAGEM = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; line-height: 1.4; color: #111; }
h1 { font-size: 17pt; color: #1f3b63; border-bottom: 2px solid #1f3b63; padding-bottom: 4px; }
h1.parte { page-break-before: always; }
h2 { font-size: 13pt; color: #1f3b63; margin-top: 18px; }
h3 { font-size: 11pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 8.5pt; }
th, td { border: 1px solid #b8c2cc; padding: 3px 5px; vertical-align: top; }
th { background: #e8eef5; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, monospace; font-size: 8.5pt; background: #f2f4f7; padding: 0 2px; }
pre { background: #f2f4f7; border: 1px solid #d5dbe2; padding: 6px; font-size: 8pt;
      white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%; display: block; margin: 8px auto; page-break-inside: avoid; }
blockquote { border-left: 4px solid #1f3b63; margin: 8px 0; padding: 4px 10px;
             background: #f5f8fb; }
.capa { text-align: center; margin-top: 60mm; }
.capa h1 { border: none; font-size: 22pt; }
.capa p { font-size: 12pt; margin: 6px; }
.sumario li { margin: 4px 0; font-size: 11pt; }
"""


def trecho(texto: str, inicio: str | None, fim: str | None) -> str:
    """Recorta o texto entre dois títulos (o de início entra, o de fim não).

    Raises:
        ValueError: título de recorte não encontrado.
    """
    if inicio is not None:
        if inicio not in texto:
            raise ValueError(f"título de início não encontrado: {inicio}")
        texto = texto[texto.index(inicio) :]
    if fim is not None:
        if fim not in texto:
            raise ValueError(f"título de fim não encontrado: {fim}")
        texto = texto[: texto.index(fim)]
    return texto


def ajustar_referencias(texto: str, pasta: Path) -> str:
    """Troca imagens relativas por caminho absoluto e links internos por texto simples.

    Raises:
        FileNotFoundError: imagem citada que não existe (evidência faltando).
    """

    def imagem(m: re.Match[str]) -> str:
        caminho = (pasta / m.group(2)).resolve()
        if not caminho.is_file():
            raise FileNotFoundError(f"imagem citada não existe: {caminho}")
        return f"![{m.group(1)}]({caminho.as_uri()})"

    def link(m: re.Match[str]) -> str:
        return m.group(0) if m.group(2).startswith("http") else m.group(1)

    return LINK.sub(link, IMAGEM.sub(imagem, texto))


def capa_e_sumario(entrega: Entrega) -> str:
    """HTML da capa (identificação e versão do código) e do sumário."""
    itens = "".join(
        f"<li>{i}. {html.escape(t)}</li>" for i, (t, *_) in enumerate(entrega.partes, 1)
    )
    versao = html.escape(versao_do_codigo(ignorar=("entregas/",)))  # a própria saída não conta
    return (
        f'<div class="capa"><h1>Link de Comunicação SDR<br>{html.escape(entrega.titulo)}</h1>'
        "<p>SCM22108 Sistemas de Comunicação, Engenharia Eletrônica, IFSC</p>"
        "<p>Gabriel de Oliveira Peres, matrícula 201920800001</p>"
        f"<p>{date.today():%d/%m/%Y}</p>"
        f"<p><small>Versão do código: <code>{versao}</code>"
        "<br>Repositório: Sistema_comunicacao_projeto_radio_digital</small></p></div>"
        f'<h1 class="parte">Sumário</h1><ol class="sumario" style="list-style:none">{itens}</ol>'
    )


ITEM_DE_LISTA = re.compile(r"^\s*(?:[-*]|\d+\.) ")
RECUO_ANINHADO = "    "  # o python-markdown exige 4 espaços para lista aninhada


def _ajustar_linha(linha: str, anterior: str) -> list[str]:
    """Uma linha fora de bloco de código, já ajustada (com a linha em branco que faltar)."""
    if not ITEM_DE_LISTA.match(linha):
        return [linha]
    recuo = len(linha) - len(linha.lstrip(" "))
    ajustada = RECUO_ANINHADO + linha.lstrip(" ") if 0 < recuo < len(RECUO_ANINHADO) else linha
    paragrafo_antes = (
        anterior.strip()
        and not ITEM_DE_LISTA.match(anterior)
        and not anterior.startswith((" ", "|", ">"))
    )
    return ["", ajustada] if paragrafo_antes else [ajustada]


def normalizar_listas(texto: str) -> str:
    """Ajusta listas do Markdown do GitHub para o python-markdown.

    O python-markdown exige 4 espaços para lista aninhada (os documentos usam 3,
    alinhados ao texto do item numerado) e uma linha em branco antes da lista.
    Blocos de código (logs) ficam como estão.
    """
    saida: list[str] = []
    em_codigo = False
    for linha in texto.split("\n"):
        if linha.lstrip().startswith("```"):
            em_codigo = not em_codigo
        if em_codigo:
            saida.append(linha)
            continue
        saida.extend(_ajustar_linha(linha, saida[-1] if saida else ""))
    return "\n".join(saida)


def montar_html(entrega: Entrega) -> str:
    """Junta capa, sumário e as partes num documento HTML só."""
    conversor = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    corpo = [capa_e_sumario(entrega)]
    for n, (titulo, arquivo, inicio, fim) in enumerate(entrega.partes, 1):
        caminho = DOCS / arquivo
        texto = trecho(caminho.read_text(encoding="utf-8"), inicio, fim)
        texto = re.sub(r"\A# [^\n]*\n", "", texto)  # o título da parte substitui o do documento
        texto = normalizar_listas(texto)
        texto = ajustar_referencias(texto, caminho.parent)
        corpo.append(f'<h1 class="parte">{n}. {html.escape(titulo)}</h1>')
        corpo.append(conversor.reset().convert(texto))
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>{html.escape(entrega.titulo)}</title><style>{CSS}</style></head>"
        f"<body>{''.join(corpo)}</body></html>"
    )


def imprimir_pdf(pagina: Path, saida: Path) -> None:
    """Imprime o HTML em PDF com o navegador em modo headless.

    Raises:
        RuntimeError: nenhum navegador encontrado ou a impressão falhou.
    """
    navegador = next((n for n in NAVEGADORES if n.is_file()), None)
    if navegador is None:
        raise RuntimeError("Edge ou Chrome não encontrado para imprimir o PDF")
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.unlink(missing_ok=True)
    comando = [
        str(navegador),
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--allow-file-access-from-files",
        f"--print-to-pdf={saida}",
        pagina.as_uri(),
    ]
    subprocess.run(comando, check=False, timeout=TEMPO_MAX_IMPRESSAO_S, capture_output=True)
    if not saida.is_file() or saida.stat().st_size == 0:
        raise RuntimeError(f"o navegador não gerou o PDF: {saida}")


def main() -> int:
    """Gera o HTML intermediário e o PDF da entrega pedida (padrão: etapas-1-2)."""
    chave = sys.argv[1] if len(sys.argv) > 1 else "etapas-1-2"
    if chave not in ENTREGAS:
        print(f"entrega desconhecida: {chave}; opções: {', '.join(ENTREGAS)}")
        return 2
    entrega = ENTREGAS[chave]
    pagina = RAIZ / "entregas" / f"{entrega.arquivo}.html"
    saida = RAIZ / "entregas" / f"{entrega.arquivo}.pdf"
    pagina.parent.mkdir(parents=True, exist_ok=True)
    pagina.write_text(montar_html(entrega), encoding="utf-8", newline="\n")
    imprimir_pdf(pagina, saida)
    print(f"PDF gerado: {saida} ({saida.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

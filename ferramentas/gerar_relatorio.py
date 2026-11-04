"""Gera o PDF do relatório de uma entrega a partir dos documentos Markdown de docs/.

Os documentos do repositório são a fonte única: o relatório só os junta na
ordem da entrega, com capa e sumário, e imprime em PDF pelo Edge (ou Chrome)
em modo headless. Assim o PDF nunca diverge do que está versionado.

Uso: python -m ferramentas.gerar_relatorio
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown  # type: ignore[import-untyped]

from sdrlink.registro import RAIZ, versao_do_codigo

DOCS = RAIZ / "docs"
SAIDA = RAIZ / "entregas" / "Relatorio_Etapas_1_2_Gabriel_Peres.pdf"
NAVEGADORES = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
)
TEMPO_MAX_IMPRESSAO_S = 120

# (título da parte, arquivo, título de seção onde começa, título onde termina)
PARTES = (
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
)

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


def capa_e_sumario() -> str:
    """HTML da capa (identificação e versão do código) e do sumário."""
    itens = "".join(f"<li>{i}. {html.escape(t)}</li>" for i, (t, *_) in enumerate(PARTES, 1))
    return (
        '<div class="capa"><h1>Link de Comunicação SDR<br>Relatório das Etapas 1 e 2</h1>'
        "<p>SCM22108 Sistemas de Comunicação, Engenharia Eletrônica, IFSC</p>"
        "<p>Gabriel de Oliveira Peres, matrícula 201920800001</p>"
        f"<p>{date.today():%d/%m/%Y}</p>"
        f"<p><small>Versão do código: <code>{html.escape(versao_do_codigo())}</code>"
        "<br>Repositório: Sistema_comunicacao_projeto_radio_digital</small></p></div>"
        f'<h1 class="parte">Sumário</h1><ol class="sumario" style="list-style:none">{itens}</ol>'
    )


def montar_html() -> str:
    """Junta capa, sumário e as partes num documento HTML só."""
    conversor = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    corpo = [capa_e_sumario()]
    for n, (titulo, arquivo, inicio, fim) in enumerate(PARTES, 1):
        caminho = DOCS / arquivo
        texto = trecho(caminho.read_text(encoding="utf-8"), inicio, fim)
        texto = re.sub(r"\A# [^\n]*\n", "", texto)  # o título da parte substitui o do documento
        texto = ajustar_referencias(texto, caminho.parent)
        corpo.append(f'<h1 class="parte">{n}. {html.escape(titulo)}</h1>')
        corpo.append(conversor.reset().convert(texto))
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>Relatório Etapas 1 e 2</title><style>{CSS}</style></head>"
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
    """Gera o HTML intermediário e o PDF da entrega."""
    pagina = RAIZ / "entregas" / "relatorio_etapas_1_2.html"
    pagina.parent.mkdir(parents=True, exist_ok=True)
    pagina.write_text(montar_html(), encoding="utf-8", newline="\n")
    imprimir_pdf(pagina, SAIDA)
    print(f"PDF gerado: {SAIDA} ({SAIDA.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

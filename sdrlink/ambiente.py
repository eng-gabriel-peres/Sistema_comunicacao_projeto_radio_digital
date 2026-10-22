"""Diagnóstico do ambiente de desenvolvimento e do hardware SDR.

Verifica se as bibliotecas do projeto carregam e se o RTL-SDR e o
ADALM-Pluto estão acessíveis. Só lê o estado do sistema, não altera nada.

Requisitos atendidos: PRC-01 (código executável e documentado); apoio a PLT-01.

Desvio justificado da regra 8 (sem import dinâmico): `verificar_modulo` usa
`importlib.import_module` porque o objetivo do módulo é justamente testar se
cada biblioteca carrega, sem derrubar o diagnóstico quando uma delas falta.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass

VERSAO_PYTHON_MINIMA = (3, 10)
MODULOS_DO_PROJETO = ("numpy", "scipy", "matplotlib", "rtlsdr", "iio", "adi")

# Exceções que as bibliotecas de hardware levantam quando a biblioteca C do
# sistema (libiio, librtlsdr) não está instalada: o pylibiio, por exemplo,
# levanta TypeError quando não encontra a libiio.dll.
ERROS_DE_CARGA = (ImportError, OSError, TypeError)


@dataclass(frozen=True)
class ItemAmbiente:
    """Resultado de uma verificação do ambiente.

    Attributes:
        nome: o que foi verificado.
        ok: True quando está pronto para uso.
        detalhe: versão encontrada ou motivo da falha.
    """

    nome: str
    ok: bool
    detalhe: str


def verificar_python() -> ItemAmbiente:
    """Confere se a versão do Python atende ao mínimo do projeto."""
    atual = sys.version_info[:3]
    ok = atual >= VERSAO_PYTHON_MINIMA
    detalhe = ".".join(str(parte) for parte in atual)
    if not ok:
        detalhe += f" (mínimo {VERSAO_PYTHON_MINIMA[0]}.{VERSAO_PYTHON_MINIMA[1]})"
    return ItemAmbiente("python", ok, detalhe)


def verificar_modulo(nome: str) -> ItemAmbiente:
    """Tenta importar um módulo e devolve a versão ou o erro.

    Args:
        nome: nome do módulo Python (ex.: "numpy").

    Raises:
        ValueError: se o nome estiver vazio.
    """
    if not nome.strip():
        raise ValueError("nome do módulo vazio")
    try:
        modulo = importlib.import_module(nome)
    except ERROS_DE_CARGA as erro:
        return ItemAmbiente(nome, False, f"{type(erro).__name__}: {erro}")
    versao = getattr(modulo, "__version__", None) or getattr(modulo, "version", "sem versão")
    return ItemAmbiente(nome, True, str(versao))


def verificar_rtl() -> ItemAmbiente:
    """Conta os dongles RTL-SDR e tenta abrir o primeiro."""
    try:
        from rtlsdr import RtlSdr, librtlsdr  # noqa: PLC0415 (só carrega se for usar)
    except ERROS_DE_CARGA as erro:
        return ItemAmbiente("rtl-sdr", False, f"biblioteca não carrega: {erro}")
    quantidade = int(librtlsdr.rtlsdr_get_device_count())
    if quantidade == 0:
        return ItemAmbiente("rtl-sdr", False, "nenhum dongle conectado")
    try:
        radio = RtlSdr(device_index=0)
    except OSError as erro:
        dica = "instalar o driver WinUSB com o Zadig (docs/ambiente.md)"
        return ItemAmbiente("rtl-sdr", False, f"{quantidade} visto(s), não abre: {erro}; {dica}")
    sintonizador = str(radio.get_tuner_type())
    radio.close()
    return ItemAmbiente(
        "rtl-sdr", True, f"{quantidade} dongle(s), índice 0 abre, tuner {sintonizador}"
    )


def verificar_pluto() -> ItemAmbiente:
    """Procura um ADALM-Pluto pelos contextos que a libiio enxerga."""
    try:
        import iio  # noqa: PLC0415 (só carrega se for usar)
    except ERROS_DE_CARGA as erro:
        motivo = f"{type(erro).__name__}; instalar a libiio 0.25 (docs/ambiente.md)"
        return ItemAmbiente("adalm-pluto", False, f"libiio não carrega ({motivo})")
    contextos: dict[str, str] = dict(iio.scan_contexts())
    plutos = [uri for uri, descricao in contextos.items() if "pluto" in descricao.lower()]
    if not plutos:
        return ItemAmbiente("adalm-pluto", False, "nenhum Pluto encontrado")
    return ItemAmbiente("adalm-pluto", True, ", ".join(plutos))


def diagnosticar() -> list[ItemAmbiente]:
    """Roda todas as verificações, na ordem: Python, bibliotecas, hardware."""
    itens = [verificar_python()]
    itens.extend(verificar_modulo(nome) for nome in MODULOS_DO_PROJETO)
    itens.append(verificar_rtl())
    itens.append(verificar_pluto())
    return itens


def formatar(itens: list[ItemAmbiente]) -> str:
    """Monta uma tabela de texto com o resultado do diagnóstico.

    Raises:
        ValueError: se a lista estiver vazia.
    """
    if not itens:
        raise ValueError("nenhum item para formatar")
    largura = max(len(item.nome) for item in itens)
    linhas = [
        f"{'OK  ' if item.ok else 'FALTA'} {item.nome:<{largura}}  {item.detalhe}" for item in itens
    ]
    return "\n".join(linhas)

"""Configuração do projeto lida de configs/*.toml (fonte única dos parâmetros).

Dois arquivos:
    configs/rtl.toml     correção de frequência do RTL-SDR adotada pela equipe. Toda
                         captura usa esse valor quando nenhum outro é pedido.
    configs/perfis.toml  perfis de enlace com nome (modulação, pulso, taxas,
                         deslocamento, LO). O TX, a gravação e o RX leem o mesmo
                         perfil, e um parâmetro dado na linha de comando substitui
                         só aquele campo.

Os dois servem para TX, RX e calibração nunca ficarem com valores diferentes (achado A14).

Requisitos: PRC-01 (parâmetros configuráveis), CAL-01 (correção registrada),
CMP-B (configuração registrada em cada posição, reconfiguração em até 5 min).
"""

from __future__ import annotations

import argparse
import dataclasses
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from sdrlink import modem
from sdrlink.modem import MODULACOES, PULSOS_FSK, PULSOS_LINEARES, ConfigModem

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_RTL = RAIZ / "configs" / "rtl.toml"
ARQUIVO_PERFIS = RAIZ / "configs" / "perfis.toml"
CORRECAO_MAXIMA_PPM = 200
TOLERANCIA_SPS = 1e-9  # folga numérica ao conferir que as amostras por símbolo são inteiras
LIMIAR_PADRAO = 0.5  # o mesmo de receptor.LIMIAR_PADRAO (teste confere)
FAIXA_LO_HZ = (915e6, 928e6)  # faixa autorizada (PLT-05); a conferência fina é do pluto_tx


def ler_correcao_ppm(arquivo: Path) -> int:
    """Lê [calibracao].correcao_ppm de um arquivo TOML e valida o valor.

    Raises:
        FileNotFoundError: arquivo inexistente.
        ValueError: chave ausente, valor não inteiro ou fora de ±200 ppm.
    """
    with arquivo.open("rb") as fp:
        dados = tomllib.load(fp)
    valor = dados.get("calibracao", {}).get("correcao_ppm")
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise ValueError(f"{arquivo}: [calibracao].correcao_ppm ausente ou não inteiro")
    if abs(valor) > CORRECAO_MAXIMA_PPM:
        raise ValueError(f"{arquivo}: correção de {valor} ppm fora de ±{CORRECAO_MAXIMA_PPM}")
    return valor


@cache
def correcao_rtl_ppm_padrao() -> int:
    """Correção adotada pela equipe (configs/rtl.toml), lida uma vez por execução."""
    return ler_correcao_ppm(ARQUIVO_RTL)


@dataclass(frozen=True)
class Perfil:
    """Parâmetros de enlace que o TX, a gravação e o RX precisam ter iguais.

    Attributes:
        nome: nome do perfil (ou "linha de comando").
        modulacao, pulso, sps, beta, bt, h: os de sdrlink.modem.ConfigModem.
        taxa_sps: taxa do DAC do Pluto e do RTL (a mesma dos dois lados).
        deslocamento_hz: posição do sinal em relação ao LO.
        lo_hz: frequência do LO do Pluto e do centro do RTL.
        fec: código convolucional no corpo dos quadros (sdrlink.codigo, bloco 09).
        emendar_caudas: TX com as caudas do RRC somadas entre quadros (bloco 12).
        limiar: limiar da métrica de detecção do RX (bloco 19: 0,4 na prova B com FEC).
        descricao: para que serve o perfil.
    """

    nome: str
    modulacao: str
    pulso: str
    sps: int
    beta: float = 0.35
    bt: float = 0.5
    h: float = 1.0
    taxa_sps: float = 2.048e6
    deslocamento_hz: float = 250e3
    lo_hz: float = 919.5e6
    fec: bool = False
    emendar_caudas: bool = False
    limiar: float = LIMIAR_PADRAO
    descricao: str = ""

    def __post_init__(self) -> None:
        """Valida pela construção do modem e pelos limites das taxas e do LO.

        Raises:
            ValueError: parâmetro inválido.
        """
        self.modem()
        if self.taxa_sps <= 0 or abs(self.deslocamento_hz) >= self.taxa_sps / 2:
            raise ValueError(f"{self.nome}: taxa ou deslocamento inválidos")
        if not 0 < self.limiar < 1:
            raise ValueError(f"{self.nome}: limiar de detecção fora de (0, 1): {self.limiar}")
        if self.emendar_caudas and not self.modem().linear:
            raise ValueError(f"{self.nome}: emendar_caudas só vale para modulações lineares")
        if not FAIXA_LO_HZ[0] <= self.lo_hz <= FAIXA_LO_HZ[1]:
            raise ValueError(f"{self.nome}: LO de {self.lo_hz / 1e6} MHz fora de 915 a 928 MHz")

    @property
    def taxa_bits(self) -> float:
        """Taxa de bits do corpo (dois bits por símbolo na DQPSK, três na 8-PSK)."""
        return self.taxa_sps / self.sps * self.modem().bits_por_simbolo

    def modem(self) -> ConfigModem:
        """Configuração do modulador e do demodulador."""
        return ConfigModem(self.modulacao, self.pulso, self.sps, self.beta, self.bt, self.h)


CAMPOS_PERFIL = tuple(c.name for c in dataclasses.fields(Perfil) if c.name != "nome")
_TIPOS = {
    "modulacao": str,
    "pulso": str,
    "descricao": str,
    "sps": int,
    "fec": bool,
    "emendar_caudas": bool,
}
Valor = str | float | bool  # valor de um campo de perfil (int é aceito como float)


def _valor(nome_perfil: str, campo: str, valor: object) -> Valor:
    """Confere o tipo de um campo lido do TOML (int aceito onde se espera float).

    Raises:
        ValueError: campo desconhecido ou de tipo errado.
    """
    if campo not in CAMPOS_PERFIL:
        raise ValueError(f"perfil {nome_perfil}: campo desconhecido {campo!r}")
    tipo = _TIPOS.get(campo, float)
    if tipo is bool and isinstance(valor, bool):
        return valor
    if not isinstance(valor, bool):
        if tipo is str and isinstance(valor, str):
            return valor
        if tipo is int and isinstance(valor, int):
            return valor
        if tipo is float and isinstance(valor, int | float):
            return float(valor)
    raise ValueError(f"perfil {nome_perfil}: {campo} = {valor!r} não é {tipo.__name__}")


def ler_perfis(arquivo: Path) -> dict[str, Perfil]:
    """Todos os perfis de um arquivo TOML, uma tabela por perfil.

    Raises:
        FileNotFoundError: arquivo inexistente.
        ValueError: arquivo sem perfis, campo desconhecido, de tipo errado ou inválido.
    """
    with arquivo.open("rb") as fp:
        dados = tomllib.load(fp)
    tabelas = {k: v for k, v in dados.items() if isinstance(v, dict)}
    if not tabelas or len(tabelas) != len(dados):
        raise ValueError(f"{arquivo}: esperado um ou mais perfis, cada um numa tabela [nome]")
    perfis = {}
    for nome, campos in tabelas.items():
        valores = {c: _valor(nome, c, v) for c, v in campos.items()}
        perfis[nome] = Perfil(nome, **valores)  # type: ignore[arg-type]
    return perfis


def perfil(nome: str, arquivo: Path = ARQUIVO_PERFIS) -> Perfil:
    """O perfil com esse nome.

    Raises:
        ValueError: perfil inexistente (a mensagem lista os disponíveis).
    """
    perfis = ler_perfis(arquivo)
    if nome not in perfis:
        raise ValueError(f"perfil {nome!r} não existe; disponíveis: {', '.join(perfis)}")
    return perfis[nome]


def montar_perfil(
    nome: str | None, explicitos: dict[str, Valor | None], arquivo: Path = ARQUIVO_PERFIS
) -> Perfil:
    """Perfil pedido com os campos dados na linha de comando por cima.

    `explicitos` traz os campos de CAMPOS_PERFIL e, opcionalmente, "taxa_bits"
    (convertida em sps); None quer dizer "não informado". Sem perfil, modulação,
    pulso e taxa de bits são obrigatórios e o resto fica no padrão de Perfil.

    Raises:
        ValueError: perfil inexistente, campo obrigatório faltando, campo
            desconhecido ou taxa de bits que não divide a taxa de amostragem.
    """
    dados = {k: v for k, v in explicitos.items() if v is not None}
    desconhecidos = set(dados) - set(CAMPOS_PERFIL) - {"taxa_bits"}
    if desconhecidos:
        raise ValueError(f"campos desconhecidos: {sorted(desconhecidos)}")
    taxa_bits = dados.pop("taxa_bits", None)
    base = perfil(nome, arquivo) if nome is not None else None
    if base is None and (taxa_bits is None or {"modulacao", "pulso"} - set(dados)):
        raise ValueError("sem --perfil, informe --modulacao, --pulso e --taxa-bits")
    if taxa_bits is not None:
        taxa_sps = float(dados.get("taxa_sps", base.taxa_sps if base else Perfil.taxa_sps))
        modulacao = str(dados.get("modulacao", base.modulacao if base else ""))
        sps = taxa_sps * modem.bits_por_simbolo_de(modulacao) / float(taxa_bits)
        if abs(sps - round(sps)) > TOLERANCIA_SPS:
            raise ValueError(
                f"amostras por símbolo = {sps:.4f}: precisa ser inteiro "
                "(taxa de amostragem × bits por símbolo / taxa de bits)"
            )
        dados["sps"] = round(sps)
    if base is None:
        return Perfil("linha de comando", **dados)  # type: ignore[arg-type]
    if not dados:
        return base
    return dataclasses.replace(base, nome=f"{base.nome} (alterado)", **dados)  # type: ignore[arg-type]


def argumentos_de_enlace(p: argparse.ArgumentParser) -> None:
    """Parâmetros de enlace comuns ao TX e ao RX: --perfil e os campos que o substituem."""
    p.add_argument("--perfil", default=None, help="perfil de configs/perfis.toml")
    p.add_argument("--modulacao", choices=MODULACOES, default=None)
    p.add_argument("--pulso", choices=PULSOS_LINEARES + PULSOS_FSK[1:], default=None)
    p.add_argument("--taxa-bits", type=float, default=None)
    p.add_argument("--beta", type=float, default=None, help="fator de rolagem do RRC")
    p.add_argument("--taxa-sps", type=float, default=None, help="padrão: 2,048 MS/s")
    p.add_argument("--deslocamento-hz", type=float, default=None, help="sinal em relação ao LO")
    p.add_argument("--lo-hz", type=float, default=None, help="padrão: 919,5 MHz (decisão D5)")
    p.add_argument(
        "--fec",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="código convolucional no corpo dos quadros (--no-fec desliga o do perfil)",
    )
    p.add_argument(
        "--emendar-caudas",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="TX com as caudas do RRC somadas entre quadros (--no-emendar-caudas desliga)",
    )


def perfil_dos_argumentos(p: argparse.ArgumentParser, args: argparse.Namespace) -> Perfil:
    """Perfil pedido na linha de comando; um erro encerra o script com a mensagem."""
    campos = (
        "modulacao",
        "pulso",
        "taxa_bits",
        "beta",
        "taxa_sps",
        "deslocamento_hz",
        "lo_hz",
        "fec",
        "emendar_caudas",
    )
    try:
        return montar_perfil(args.perfil, {c: getattr(args, c) for c in campos})
    except ValueError as erro:
        p.error(str(erro))

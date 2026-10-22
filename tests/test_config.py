"""Testes da configuração (sdrlink.config) e do uso do valor padrão."""

from pathlib import Path

import pytest

from sdrlink import config
from sdrlink.fm import erro_absoluto_ppm
from sdrlink.hw.rtl_rx import ConfigRtl


def test_correcao_adotada_e_77_ppm() -> None:
    assert config.ler_correcao_ppm(config.ARQUIVO_RTL) == 77
    assert config.correcao_rtl_ppm_padrao() == 77


def test_captura_sem_correcao_explicita_usa_a_configuracao() -> None:
    assert ConfigRtl(915e6, 2.048e6, 20.0).correcao_ppm == 77
    assert ConfigRtl(915e6, 2.048e6, 20.0, 0).correcao_ppm == 0


@pytest.mark.parametrize(
    ("conteudo", "mensagem"),
    [
        ("[calibracao]\n", "ausente"),
        ("[calibracao]\ncorrecao_ppm = 77.5\n", "não inteiro"),
        ("[calibracao]\ncorrecao_ppm = true\n", "não inteiro"),
        ("[calibracao]\ncorrecao_ppm = 500\n", "fora"),
    ],
)
def test_configuracao_invalida_e_rejeitada(tmp_path: Path, conteudo: str, mensagem: str) -> None:
    arquivo = tmp_path / "rtl.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError, match=mensagem):
        config.ler_correcao_ppm(arquivo)


def test_arquivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        config.ler_correcao_ppm(tmp_path / "nao_existe.toml")


def test_erro_absoluto_desconta_a_correcao_aplicada() -> None:
    # medido +8,7 ppm com 77 aplicados -> o RTL sozinho erra -68,3 ppm
    assert erro_absoluto_ppm(8.7, 77) == pytest.approx(-68.3)
    assert erro_absoluto_ppm(-68.3, 0) == pytest.approx(-68.3)
    with pytest.raises(ValueError, match="plausível"):
        erro_absoluto_ppm(0.0, 500)

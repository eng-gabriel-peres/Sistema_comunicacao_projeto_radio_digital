"""Testes do diagnóstico de ambiente (sdrlink.ambiente)."""

import pytest

from sdrlink import ambiente
from sdrlink.ambiente import ItemAmbiente


def test_python_atende_minimo() -> None:
    assert ambiente.verificar_python().ok


def test_python_abaixo_do_minimo_e_acusado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ambiente, "VERSAO_PYTHON_MINIMA", (99, 0))
    item = ambiente.verificar_python()
    assert not item.ok
    assert "mínimo 99.0" in item.detalhe


def test_modulo_existente_retorna_versao() -> None:
    item = ambiente.verificar_modulo("numpy")
    assert item.ok
    assert item.detalhe[0].isdigit()


def test_modulo_inexistente_nao_derruba_o_diagnostico() -> None:
    item = ambiente.verificar_modulo("modulo_que_nao_existe_xyz")
    assert not item.ok
    assert "ModuleNotFoundError" in item.detalhe


def test_nome_de_modulo_vazio_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="vazio"):
        ambiente.verificar_modulo("  ")


def test_formatar_marca_ok_e_falta() -> None:
    itens = [ItemAmbiente("numpy", True, "2.5"), ItemAmbiente("iio", False, "não carrega")]
    linhas = ambiente.formatar(itens).splitlines()
    assert linhas[0].startswith("OK")
    assert linhas[1].startswith("FALTA")


def test_formatar_lista_vazia_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="nenhum item"):
        ambiente.formatar([])


@pytest.mark.hardware
def test_rtl_sdr_abre() -> None:
    item = ambiente.verificar_rtl()
    assert item.ok, item.detalhe


@pytest.mark.hardware
def test_pluto_encontrado() -> None:
    item = ambiente.verificar_pluto()
    assert item.ok, item.detalhe

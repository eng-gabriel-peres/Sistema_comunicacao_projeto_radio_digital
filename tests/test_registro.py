"""Testes do registro de ensaios (sdrlink.registro)."""

import json
import re
from pathlib import Path

import pytest

from sdrlink import registro


def _git_falso(versao: str | None, pendencias: str | None) -> object:
    """Substituto de registro._git com respostas fixas."""
    return lambda nome: versao if nome == "versao" else pendencias


def test_versao_real_tem_formato_valido() -> None:
    versao = registro.versao_do_codigo()
    assert versao == "desconhecida" or re.fullmatch(r"[\w.-]+", versao)


def test_versao_sem_pendencias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registro, "_git", _git_falso("bloco-01", ""))
    assert registro.versao_do_codigo() == "bloco-01"


def test_versao_com_arquivo_novo_fora_do_git_fica_suja(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registro, "_git", _git_falso("bloco-01", "?? scripts/novo.py"))
    assert registro.versao_do_codigo() == "bloco-01-sujo"


def test_versao_sem_git_e_desconhecida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registro, "_git", _git_falso(None, None))
    assert registro.versao_do_codigo() == "desconhecida"


def test_comando_git_desconhecido_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="desconhecido"):
        registro._git("push")


def test_carimbo_de_tempo_tem_formato_fixo() -> None:
    assert re.fullmatch(r"\d{8}_\d{6}", registro.carimbo_de_tempo())


def test_salvar_json_cria_pasta_e_preserva_acentos(tmp_path: Path) -> None:
    caminho = registro.salvar_json(tmp_path / "sub" / "r.json", {"medição": 1.5})
    assert json.loads(caminho.read_text(encoding="utf-8")) == {"medição": 1.5}


def test_salvar_json_rejeita_extensao_e_vazio(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="json"):
        registro.salvar_json(tmp_path / "r.txt", {"a": 1})
    with pytest.raises(ValueError, match="nada"):
        registro.salvar_json(tmp_path / "r.json", {})

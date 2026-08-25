# -*- coding: utf-8 -*-
"""Redireciona os arquivos de persistência (perfil/histórico/estado do radar) pra um
diretório temporário em TODO teste - sem isso, os testes leriam/escreveriam em
cima de `data/` de verdade (estado real do usuário, se algum dia rodar numa máquina
com o ECHO já em uso)."""
import pytest

from echo.core import perfil as perfil_mod
from echo.core import historico as historico_mod
from echo.core import radar as radar_mod


@pytest.fixture(autouse=True)
def isolar_persistencia(tmp_path, monkeypatch):
    monkeypatch.setattr(perfil_mod, "ARQUIVO_PERFIL", str(tmp_path / "perfil.json"))
    monkeypatch.setattr(historico_mod, "ARQUIVO_HISTORICO", str(tmp_path / "historico.json"))
    monkeypatch.setattr(radar_mod, "ARQUIVO_ESTADO_RADAR", str(tmp_path / "radar_estado.json"))
    yield

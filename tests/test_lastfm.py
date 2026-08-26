# -*- coding: utf-8 -*-
from echo.providers.lastfm import _normalizar_popularidade


def test_listeners_abaixo_do_piso_vira_none():
    assert _normalizar_popularidade(10) is None
    assert _normalizar_popularidade(None) is None
    assert _normalizar_popularidade("não é número") is None


def test_listeners_no_piso_vira_zero():
    assert _normalizar_popularidade(50) == 0


def test_listeners_no_teto_vira_cem():
    assert _normalizar_popularidade(2_000_000) == 100


def test_listeners_acima_do_teto_satura_em_cem():
    assert _normalizar_popularidade(10_000_000) == 100


def test_listeners_intermediario_fica_entre_0_e_100():
    valor = _normalizar_popularidade(100_000)
    assert 0 < valor < 100

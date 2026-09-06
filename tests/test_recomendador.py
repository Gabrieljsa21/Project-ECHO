# -*- coding: utf-8 -*-
from echo.core import perfil as perfil_mod
from echo.core import recomendador as recomendador_mod

USUARIO = "111111"


def test_pesos_efetivos_equilibrado_preserva_pesos_base():
    pesos = recomendador_mod.pesos_efetivos(0.5)
    assert pesos["compatibilidade"] == recomendador_mod.PESO_COMPATIBILIDADE
    assert pesos["relevancia"] == recomendador_mod.PESO_RELEVANCIA
    assert pesos["descoberta"] == recomendador_mod.PESO_DESCOBERTA
    assert pesos["exploracao"] == recomendador_mod.PESO_EXPLORACAO


def test_pesos_efetivos_none_equivale_a_equilibrado():
    assert recomendador_mod.pesos_efetivos(None) == recomendador_mod.pesos_efetivos(0.5)


def test_pesos_efetivos_conservador_zera_descoberta_e_exploracao():
    pesos = recomendador_mod.pesos_efetivos(0.0)
    assert pesos["descoberta"] == 0.0
    assert pesos["exploracao"] == 0.0
    assert pesos["compatibilidade"] > recomendador_mod.PESO_COMPATIBILIDADE


def test_pesos_efetivos_explorador_aumenta_descoberta_e_exploracao():
    pesos = recomendador_mod.pesos_efetivos(1.0)
    assert pesos["descoberta"] > recomendador_mod.PESO_DESCOBERTA
    assert pesos["exploracao"] > recomendador_mod.PESO_EXPLORACAO
    assert pesos["compatibilidade"] < recomendador_mod.PESO_COMPATIBILIDADE


def test_pesos_efetivos_sempre_somam_um():
    for nivel in (0.0, 0.25, 0.5, 0.75, 1.0):
        pesos = recomendador_mod.pesos_efetivos(nivel)
        assert round(sum(pesos.values()), 9) == 1.0


def test_discovery_level_explorador_prioriza_obscuro_sobre_mainstream():
    """2 candidatos do MESMO gênero preferido (mesma compatibilidade) - um
    mainstream (popular) e um obscuro (baixa popularidade, maior "descoberta").
    Conservador prefere o mainstream; Explorador inverte a ordem (seção 16:
    "Explorador: aumenta Descoberta e Exploração" é sobre ranking relativo,
    não sobre o score absoluto de UM candidato isolado)."""
    perfil_mod.definir_peso_genero(USUARIO, "boom bap", 1.0)
    perfil = perfil_mod.carregar_perfil(USUARIO)
    mainstream = {"titulo": "Mainstream", "artista": "Artista M", "generos": ["boom bap"], "popularidade": 90}
    obscuro = {"titulo": "Obscuro", "artista": "Artista O", "generos": ["boom bap"], "popularidade": 5}

    perfil["discovery_level"] = 0.0
    score_mainstream_conservador, _ = recomendador_mod.calcular_score(USUARIO, mainstream, perfil)
    score_obscuro_conservador, _ = recomendador_mod.calcular_score(USUARIO, obscuro, perfil)
    assert score_mainstream_conservador > score_obscuro_conservador

    perfil["discovery_level"] = 1.0
    score_mainstream_explorador, _ = recomendador_mod.calcular_score(USUARIO, mainstream, perfil)
    score_obscuro_explorador, _ = recomendador_mod.calcular_score(USUARIO, obscuro, perfil)
    assert score_obscuro_explorador > score_mainstream_explorador

# -*- coding: utf-8 -*-
from echo.core import perfil as perfil_mod


def test_perfil_padrao_quando_nao_existe_arquivo():
    perfil = perfil_mod.carregar_perfil()
    assert perfil["favorite_artists"] == []
    assert perfil["discovery_level"] == 0.5


def test_salvar_e_carregar_preferencias():
    perfil = perfil_mod.carregar_perfil()
    perfil["preferred_genres"]["boom bap"] = 0.7
    perfil_mod.salvar_perfil(perfil)

    recarregado = perfil_mod.carregar_perfil()
    assert recarregado["preferred_genres"]["boom bap"] == 0.7


def test_persistencia_sobrevive_a_novo_carregamento_do_modulo():
    perfil_mod.adicionar_artista_favorito("MF DOOM", genero="boom bap")
    perfil = perfil_mod.carregar_perfil()
    assert any(a["nome"] == "MF DOOM" for a in perfil["favorite_artists"])
    assert perfil["preferred_genres"]["boom bap"] > 0.5


def test_adicionar_artista_favorito_remove_de_rejeitados():
    perfil_mod.adicionar_artista_rejeitado("Artista X")
    perfil_mod.adicionar_artista_favorito("Artista X")
    perfil = perfil_mod.carregar_perfil()
    assert not any(a["nome"] == "Artista X" for a in perfil["disliked_artists"])
    assert any(a["nome"] == "Artista X" for a in perfil["favorite_artists"])


def test_ajustar_peso_genero_nunca_sai_de_0_1():
    perfil = perfil_mod.carregar_perfil()
    perfil["preferred_genres"]["trap"] = 0.95
    perfil_mod.ajustar_peso_genero(perfil, "trap", 0.5)
    assert perfil["preferred_genres"]["trap"] == 1.0

    perfil["preferred_genres"]["lo-fi"] = 0.05
    perfil_mod.ajustar_peso_genero(perfil, "lo-fi", -0.5)
    assert perfil["preferred_genres"]["lo-fi"] == 0.0


def test_feedback_positivo_e_negativo_via_discovery_level():
    perfil_mod.definir_discovery_level(1.5)
    assert perfil_mod.carregar_perfil()["discovery_level"] == 1.0

    perfil_mod.definir_discovery_level(-0.3)
    assert perfil_mod.carregar_perfil()["discovery_level"] == 0.0


def test_importar_historico_adiciona_artistas_favoritos():
    artistas = [
        {"nome": "MF DOOM", "rank": 1, "generos": ["boom bap"]},
        {"nome": "Madlib", "rank": 2, "generos": ["boom bap", "jazz rap"]},
    ]
    perfil = perfil_mod.importar_favoritos_do_historico(artistas)
    nomes = {a["nome"] for a in perfil["favorite_artists"]}
    assert nomes == {"MF DOOM", "Madlib"}
    # "boom bap" recebe o peso do artista rank 1 (mais alto); "jazz rap" só
    # aparece no rank 2 - deve ficar com peso menor
    assert perfil["preferred_genres"]["boom bap"] > perfil["preferred_genres"]["jazz rap"]


def test_importar_historico_pesa_mais_alto_ranking_maior():
    artistas = [
        {"nome": "Artista A", "rank": 1, "generos": ["jazz"]},
        {"nome": "Artista B", "rank": 50, "generos": ["jazz"]},
    ]
    perfil = perfil_mod.importar_favoritos_do_historico(artistas)
    # rank 1 sozinho já fixaria o peso de "jazz" no valor mais alto (max() entre os dois)
    assert perfil["preferred_genres"]["jazz"] == 1.0


def test_importar_historico_nunca_reimporta_artista_rejeitado():
    perfil_mod.adicionar_artista_rejeitado("Artista Odiado")
    artistas = [{"nome": "Artista Odiado", "rank": 1, "generos": ["pop"]}]
    perfil = perfil_mod.importar_favoritos_do_historico(artistas)
    assert not any(a["nome"] == "Artista Odiado" for a in perfil["favorite_artists"])


def test_importar_historico_nao_duplica_artista_ja_favorito():
    perfil_mod.adicionar_artista_favorito("MF DOOM")
    artistas = [{"nome": "MF DOOM", "rank": 1, "generos": ["boom bap"]}]
    perfil = perfil_mod.importar_favoritos_do_historico(artistas)
    assert sum(1 for a in perfil["favorite_artists"] if a["nome"] == "MF DOOM") == 1


def test_importar_historico_nunca_diminui_peso_ja_mais_alto():
    perfil_mod.definir_peso_genero("rock", 0.9)
    artistas = [{"nome": "Artista Fraco", "rank": 100, "generos": ["rock"]}]
    perfil = perfil_mod.importar_favoritos_do_historico(artistas)
    assert perfil["preferred_genres"]["rock"] == 0.9

# -*- coding: utf-8 -*-
from echo.core import historico as historico_mod


def test_detectar_musica_ja_recomendada():
    historico_mod.registrar_recomendacao("Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    assert historico_mod.foi_recomendada_recentemente("Song A", "Artista A")
    assert not historico_mod.foi_recomendada_recentemente("Song B", "Artista A")


def test_permitir_redescoberta_apos_intervalo_configurado():
    historico_mod.registrar_recomendacao("Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    # dias=0 simula "qualquer coisa recomendada antes de agora já pode ser redescoberta"
    assert not historico_mod.foi_recomendada_recentemente("Song A", "Artista A", dias=-1)


def test_registrar_feedback_e_data():
    historico_mod.registrar_recomendacao("Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    track_id = historico_mod._track_id("Song A", "Artista A")

    entrada = historico_mod.registrar_feedback(track_id, "positivo")
    assert entrada["user_feedback"] == "positivo"
    assert entrada["recommended_at"]

    historico = historico_mod.obter_historico()
    assert historico[0]["user_feedback"] == "positivo"


def test_feedback_em_track_inexistente_devolve_none():
    assert historico_mod.registrar_feedback("artista::musica-que-nao-existe", "positivo") is None


def test_artista_tem_feedback_negativo():
    historico_mod.registrar_recomendacao("Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    track_id = historico_mod._track_id("Song A", "Artista A")
    historico_mod.registrar_feedback(track_id, "negativo")
    assert historico_mod.artista_tem_feedback_negativo("Artista A")
    assert not historico_mod.artista_tem_feedback_negativo("Artista B")

# -*- coding: utf-8 -*-
from echo.core import em_alta as em_alta_mod
from echo.core import historico as historico_mod

USUARIO = "111111"


def _candidato(titulo, artista, popularidade):
    return {"titulo": titulo, "artista": artista, "generos": [], "popularidade": popularidade}


def test_ordena_por_popularidade_decrescente():
    candidatos = [
        _candidato("Song A", "Artista A", 40),
        _candidato("Song B", "Artista B", 90),
        _candidato("Song C", "Artista C", 60),
    ]
    resultado = em_alta_mod.obter_em_alta(USUARIO, candidatos)
    assert [c["titulo"] for c in resultado] == ["Song B", "Song C", "Song A"]


def test_limita_uma_faixa_por_artista():
    candidatos = [
        _candidato("Song A", "Mesmo Artista", 90),
        _candidato("Song B", "Mesmo Artista", 80),
    ]
    resultado = em_alta_mod.obter_em_alta(USUARIO, candidatos)
    assert len(resultado) == 1
    assert resultado[0]["titulo"] == "Song A"


def test_nao_repete_faixa_recomendada_recentemente():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="radar", category="relevancia")
    candidatos = [_candidato("Song A", "Artista A", 90), _candidato("Song B", "Artista B", 50)]
    resultado = em_alta_mod.obter_em_alta(USUARIO, candidatos)
    assert [c["titulo"] for c in resultado] == ["Song B"]


def test_candidato_sem_popularidade_fica_no_fim():
    candidatos = [_candidato("Song Sem Dado", "Artista X", None), _candidato("Song Com Dado", "Artista Y", 10)]
    resultado = em_alta_mod.obter_em_alta(USUARIO, candidatos)
    assert [c["titulo"] for c in resultado] == ["Song Com Dado", "Song Sem Dado"]


def test_respeita_quantidade():
    candidatos = [_candidato(f"Song {i}", f"Artista {i}", i) for i in range(20)]
    resultado = em_alta_mod.obter_em_alta(USUARIO, candidatos, quantidade=5)
    assert len(resultado) == 5


def test_registra_selecao_no_historico_como_em_alta():
    candidatos = [_candidato("Song A", "Artista A", 90)]
    em_alta_mod.obter_em_alta(USUARIO, candidatos)
    historico = historico_mod.obter_historico(USUARIO)
    assert historico[0]["category"] == "em_alta"

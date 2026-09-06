# -*- coding: utf-8 -*-
from datetime import date, timedelta

from echo.core import historico as historico_mod
from echo.core import redescobertas as redescobertas_mod

USUARIO = "111111"


def _aprovar_faixa_ha_dias(titulo, artista, dias_atras):
    historico_mod.registrar_recomendacao(USUARIO, titulo, artista, reason="radar", category="compatibilidade")
    track_id = historico_mod.track_id(titulo, artista)
    historico_mod.registrar_feedback(USUARIO, track_id, "positivo")
    historico = historico_mod.carregar_historico()
    for entrada in historico:
        if entrada["track_id"] == track_id:
            entrada["recommended_at"] = (date.today() - timedelta(days=dias_atras)).isoformat()
    historico_mod._salvar_historico(historico)


def test_nao_sugere_faixa_recente():
    _aprovar_faixa_ha_dias("Song Recente", "Artista A", dias_atras=10)
    assert redescobertas_mod.obter_redescobertas(USUARIO) == []


def test_sugere_faixa_aprovada_ha_muito_tempo():
    _aprovar_faixa_ha_dias("Song Antiga", "Artista B", dias_atras=200)
    resultado = redescobertas_mod.obter_redescobertas(USUARIO)
    assert len(resultado) == 1
    assert resultado[0]["titulo"] == "Song Antiga"
    assert resultado[0]["dias_sem_aparecer"] == 200


def test_nao_sugere_faixa_rejeitada():
    historico_mod.registrar_recomendacao(USUARIO, "Song Ruim", "Artista C", reason="radar", category="compatibilidade")
    track_id = historico_mod.track_id("Song Ruim", "Artista C")
    historico_mod.registrar_feedback(USUARIO, track_id, "negativo")
    historico = historico_mod.carregar_historico()
    for entrada in historico:
        if entrada["track_id"] == track_id:
            entrada["recommended_at"] = (date.today() - timedelta(days=300)).isoformat()
    historico_mod._salvar_historico(historico)
    assert redescobertas_mod.obter_redescobertas(USUARIO) == []


def test_mais_esquecida_primeiro():
    _aprovar_faixa_ha_dias("Song 200 dias", "Artista D", dias_atras=200)
    _aprovar_faixa_ha_dias("Song 300 dias", "Artista E", dias_atras=300)
    resultado = redescobertas_mod.obter_redescobertas(USUARIO, quantidade=2)
    assert [c["titulo"] for c in resultado] == ["Song 300 dias", "Song 200 dias"]


def test_respeita_quantidade():
    for i in range(5):
        _aprovar_faixa_ha_dias(f"Song {i}", f"Artista {i}", dias_atras=200 + i)
    resultado = redescobertas_mod.obter_redescobertas(USUARIO, quantidade=2)
    assert len(resultado) == 2

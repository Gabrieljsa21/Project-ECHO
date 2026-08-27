# -*- coding: utf-8 -*-
from echo.core import historico as historico_mod

USUARIO = "111111"
OUTRO_USUARIO = "222222"


def test_detectar_musica_ja_recomendada():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    assert historico_mod.foi_recomendada_recentemente(USUARIO, "Song A", "Artista A")
    assert not historico_mod.foi_recomendada_recentemente(USUARIO, "Song B", "Artista A")


def test_permitir_redescoberta_apos_intervalo_configurado():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    # dias=-1 simula "qualquer coisa recomendada antes de agora já pode ser redescoberta"
    assert not historico_mod.foi_recomendada_recentemente(USUARIO, "Song A", "Artista A", dias=-1)


def test_registrar_feedback_e_data():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    track_id = historico_mod.track_id("Song A", "Artista A")

    entrada = historico_mod.registrar_feedback(USUARIO, track_id, "positivo")
    assert entrada["user_feedback"] == "positivo"
    assert entrada["recommended_at"]

    historico = historico_mod.obter_historico(USUARIO)
    assert historico[0]["user_feedback"] == "positivo"


def test_feedback_em_track_inexistente_devolve_none():
    assert historico_mod.registrar_feedback(USUARIO, "artista::musica-que-nao-existe", "positivo") is None


def test_foi_votada_so_conta_voto_de_verdade():
    """Tocar sem avaliar NÃO conta como votada (pedido do usuário
    2026-08-26: "Musicas sem voto não saem do pool") - só 👍/👎 de verdade."""
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    assert not historico_mod.foi_votada(USUARIO, "Song A", "Artista A")

    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "positivo")
    assert historico_mod.foi_votada(USUARIO, "Song A", "Artista A")
    assert not historico_mod.foi_votada(USUARIO, "Song B", "Artista A")


def test_foi_votada_negativo_tambem_conta():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "negativo")
    assert historico_mod.foi_votada(USUARIO, "Song A", "Artista A")


def test_obter_voto_devolve_none_sem_avaliacao():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    assert historico_mod.obter_voto(USUARIO, "Song A", "Artista A") is None


def test_obter_voto_devolve_o_mais_recente():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "positivo")
    assert historico_mod.obter_voto(USUARIO, "Song A", "Artista A") == "positivo"

    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "negativo")
    assert historico_mod.obter_voto(USUARIO, "Song A", "Artista A") == "negativo"


def test_historico_isolado_por_pessoa():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    assert historico_mod.foi_recomendada_recentemente(USUARIO, "Song A", "Artista A")
    assert not historico_mod.foi_recomendada_recentemente(OUTRO_USUARIO, "Song A", "Artista A")


def test_obter_aprovadas_e_desaprovadas_dedup_pela_mais_recente():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    track_id = historico_mod.track_id("Song A", "Artista A")
    historico_mod.registrar_feedback(USUARIO, track_id, "positivo")
    # segunda recomendação da MESMA faixa, com feedback negativo dessa vez
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, track_id, "negativo")

    aprovadas = historico_mod.obter_aprovadas(USUARIO)
    desaprovadas = historico_mod.obter_desaprovadas(USUARIO)
    assert len(aprovadas) == 0  # a entrada mais recente é negativa, não conta mais como aprovada
    assert len(desaprovadas) == 1
    assert desaprovadas[0]["track_id"] == track_id


def test_registrar_evento_escuta_e_contar_sinais_fracos():
    historico_mod.registrar_evento_escuta(USUARIO, "Song A", "Artista A", 0.1, pulado=True, momento_do_skip=8)
    historico_mod.registrar_evento_escuta(USUARIO, "Song B", "Artista A", 0.15, pulado=True, momento_do_skip=5)
    historico_mod.registrar_evento_escuta(USUARIO, "Song C", "Artista A", 0.9, pulado=False)

    assert historico_mod.contar_eventos_fracos_recentes(USUARIO, "Artista A", negativo=True) == 2
    assert historico_mod.contar_eventos_fracos_recentes(USUARIO, "Artista A", negativo=False) == 1

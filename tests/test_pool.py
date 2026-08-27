# -*- coding: utf-8 -*-
from echo.core import pool as pool_mod
from echo.core import historico as historico_mod

USUARIO = "111111"
OUTRO_USUARIO = "222222"


def _candidato(titulo, artista, generos, score, categoria="compatibilidade"):
    return {"titulo": titulo, "artista": artista, "generos": generos, "_score": score, "_categoria": categoria}


def test_gerar_pool_incremental_adiciona_candidatos_novos():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.7)])
    pool = pool_mod.carregar_pool(USUARIO)
    assert len(pool) == 1
    assert pool[0]["titulo"] == "Song A"
    assert pool[0]["afinidade"] == 0.7


def test_gerar_pool_incremental_nunca_recria_do_zero():
    """Chamadas sucessivas se FUNDEM - uma rodada nova não pode apagar quem já
    estava lá e ainda não foi consumido."""
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.7)])
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song B", "Artista B", ["rock"], 0.6)])
    pool = pool_mod.carregar_pool(USUARIO)
    titulos = {c["titulo"] for c in pool}
    assert titulos == {"Song A", "Song B"}


def test_gerar_pool_incremental_atualiza_score_de_quem_ja_estava():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.5)])
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.9)])
    pool = pool_mod.carregar_pool(USUARIO)
    assert len(pool) == 1
    assert pool[0]["afinidade"] == 0.9


def test_gerar_pool_incremental_preserva_descoberto_em_original():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.5)])
    descoberto_em_original = pool_mod.carregar_pool(USUARIO)[0]["descoberto_em"]

    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.9)])
    assert pool_mod.carregar_pool(USUARIO)[0]["descoberto_em"] == descoberto_em_original


def test_gerar_pool_incremental_mantem_faixa_tocada_sem_voto():
    """Pedido do usuário 2026-08-26: "Musicas sem voto não saem do pool" -
    só tocar (sem 👍/👎) não é sinal de nada, a faixa continua elegível."""
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.9)])
    assert len(pool_mod.carregar_pool(USUARIO)) == 1


def test_gerar_pool_incremental_remove_faixa_votada():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "positivo")
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.9)])
    assert pool_mod.carregar_pool(USUARIO) == []


def test_gerar_pool_incremental_respeita_tamanho_alvo():
    candidatos = [_candidato(f"Song {i}", f"Artista {i}", ["pop"], i / 100) for i in range(10)]
    pool_mod.gerar_pool_incremental(USUARIO, candidatos, tamanho_alvo=3)
    pool = pool_mod.carregar_pool(USUARIO)
    assert len(pool) == 3
    # mantém os de MAIOR afinidade, não os primeiros da lista
    assert {c["titulo"] for c in pool} == {"Song 7", "Song 8", "Song 9"}


def test_pool_isolado_por_pessoa():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.7)])
    pool_mod.gerar_pool_incremental(OUTRO_USUARIO, [_candidato("Song B", "Artista B", ["rock"], 0.6)])
    assert {c["titulo"] for c in pool_mod.carregar_pool(USUARIO)} == {"Song A"}
    assert {c["titulo"] for c in pool_mod.carregar_pool(OUTRO_USUARIO)} == {"Song B"}


def test_consumir_proxima_nao_remove_do_pool_sem_voto():
    """Pedido do usuário 2026-08-26: "Musicas sem voto não saem do pool" -
    consumir (tocar) sozinho não tira a faixa do repertório; dedup de
    sessão é responsabilidade de `excluidos_sessao`, de quem chama."""
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.7)])
    escolhida = pool_mod.consumir_proxima(USUARIO)
    assert escolhida["titulo"] == "Song A"
    assert len(pool_mod.carregar_pool(USUARIO)) == 1
    assert not historico_mod.foi_votada(USUARIO, "Song A", "Artista A")
    # ainda assim registra a recomendação (alimenta o dedup de 90 dias do Radar)
    assert historico_mod.foi_recomendada_recentemente(USUARIO, "Song A", "Artista A")


def test_consumir_proxima_pool_vazio_devolve_none():
    assert pool_mod.consumir_proxima(USUARIO) is None


def test_consumir_proxima_respeita_exclusao_de_sessao():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.9)])
    escolhida = pool_mod.consumir_proxima(USUARIO, excluidos_sessao={"artista a::song a"})
    assert escolhida is None


def test_consumir_proxima_prioriza_boost_de_mesmo_artista(monkeypatch):
    # 🔥 `consumir_proxima` sorteia entre as top N por score (2026-08-27,
    # achado real: sessão nova = exclusão vazia = sempre a mesma faixa de
    # maior afinidade em `/caos`) - aqui só verificamos a ORDEM de score
    # (quem o sorteio favorece), então travamos o sorteio no 1º da lista
    # ordenada (maior score primeiro).
    monkeypatch.setattr(pool_mod.random, "choice", lambda seq: seq[0])
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato("Song A", "Artista Semente", ["pop"], 0.5),
        _candidato("Song B", "Outro Artista", ["rock"], 0.6),
    ])
    escolhida = pool_mod.consumir_proxima(USUARIO, seed_artista="Artista Semente")
    assert escolhida["titulo"] == "Song A"


def test_consumir_proxima_prioriza_boost_de_genero_em_comum(monkeypatch):
    monkeypatch.setattr(pool_mod.random, "choice", lambda seq: seq[0])
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato("Song A", "Artista A", ["boom bap"], 0.5),
        _candidato("Song B", "Artista B", ["pop"], 0.6),
    ])
    escolhida = pool_mod.consumir_proxima(USUARIO, seed_generos=["boom bap"])
    assert escolhida["titulo"] == "Song A"


def test_consumir_proxima_aplica_penalidade_de_diversidade_de_sessao(monkeypatch):
    monkeypatch.setattr(pool_mod.random, "choice", lambda seq: seq[0])
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato("Song A", "Artista Repetido", ["pop"], 0.7),
        _candidato("Song B", "Artista Novo", ["pop"], 0.65),
    ])
    escolhida = pool_mod.consumir_proxima(
        USUARIO, penalidades_sessao={"artista::artista repetido": 3},
    )
    assert escolhida["titulo"] == "Song B"


def test_consumir_proxima_sorteia_entre_as_top_n_nao_sempre_a_mesma():
    """Sem exclusão de sessão (achado real: `/caos` chamado 3x em sessões
    novas devolvia sempre "Duvet - bôa", mesmo com o pool cheio) - com
    várias faixas de score parecido, chamadas repetidas devem variar."""
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato(f"Song {i}", f"Artista {i}", ["pop"], 0.9 - i * 0.001) for i in range(10)
    ])
    escolhidas = {pool_mod.consumir_proxima(USUARIO)["titulo"] for _ in range(30)}
    assert len(escolhidas) > 1


def test_remover_track_remove_so_a_faixa_exata():
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato("Song A", "Artista A", ["pop"], 0.7),
        _candidato("Song B", "Artista A", ["pop"], 0.6),
    ])
    pool_mod.remover_track(USUARIO, "Song A", "Artista A")
    pool = pool_mod.carregar_pool(USUARIO)
    assert {c["titulo"] for c in pool} == {"Song B"}


def test_remover_track_de_faixa_ausente_nao_quebra():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.7)])
    pool_mod.remover_track(USUARIO, "Song Inexistente", "Artista X")
    assert len(pool_mod.carregar_pool(USUARIO)) == 1


def test_pool_vazio_ou_velho_true_quando_nunca_gerado():
    assert pool_mod.pool_vazio_ou_velho(USUARIO) is True


def test_pool_vazio_ou_velho_false_apos_gerar():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato("Song A", "Artista A", ["pop"], 0.7)])
    assert pool_mod.pool_vazio_ou_velho(USUARIO) is False

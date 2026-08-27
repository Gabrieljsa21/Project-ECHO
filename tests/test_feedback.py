# -*- coding: utf-8 -*-
from echo.core import feedback as feedback_mod
from echo.core import historico as historico_mod
from echo.core import perfil as perfil_mod
from echo.core import pool as pool_mod
from echo.providers import ProvedorIndisponivel

USUARIO = "111111"


class _ProvedorFalso:
    def __init__(self, generos_por_artista=None):
        self._generos_por_artista = generos_por_artista or {}

    def resolver_generos(self, nomes_artistas):
        return {n.lower(): self._generos_por_artista.get(n.lower(), []) for n in nomes_artistas}


class _ProvedorSemGenero:
    def resolver_generos(self, nomes_artistas):
        return {n.lower(): [] for n in nomes_artistas}


class _ProvedorQuebrado:
    def resolver_generos(self, nomes_artistas):
        raise ProvedorIndisponivel("sem credencial")


def _candidato_ranqueado(titulo, artista, generos, score, categoria="compatibilidade"):
    return {"titulo": titulo, "artista": artista, "generos": generos, "_score": score, "_categoria": categoria}


def test_feedback_ao_vivo_cria_entrada_quando_faixa_nunca_foi_recomendada():
    """Botão de like/dislike no Modo Música do ERIS - a faixa tocada pode nunca
    ter passado pelo Radar (busca livre do usuário)."""
    provedor = _ProvedorFalso()
    entrada = feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Doomsday", "MF DOOM", "positivo")

    assert entrada is not None
    assert entrada["user_feedback"] == "positivo"
    assert entrada["reason"] == "modo_musica"

    historico = historico_mod.obter_historico(USUARIO)
    assert historico[0]["titulo"] == "Doomsday"


def test_feedback_ao_vivo_ajusta_peso_do_genero_resolvido():
    provedor = _ProvedorFalso(generos_por_artista={"mf doom": ["boom bap"]})
    perfil_antes = perfil_mod.carregar_perfil(USUARIO)
    assert "boom bap" not in perfil_antes["preferred_genres"]

    feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Doomsday", "MF DOOM", "positivo")

    perfil_depois = perfil_mod.carregar_perfil(USUARIO)
    assert perfil_depois["preferred_genres"]["boom bap"] == feedback_mod.AJUSTE_POSITIVO + 0.5


def test_feedback_ao_vivo_negativo_reduz_peso():
    provedor = _ProvedorFalso(generos_por_artista={"mf doom": ["boom bap"]})
    perfil_mod.definir_peso_genero(USUARIO, "boom bap", 0.5)

    feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Doomsday", "MF DOOM", "negativo")

    perfil_depois = perfil_mod.carregar_perfil(USUARIO)
    assert perfil_depois["preferred_genres"]["boom bap"] == 0.5 + feedback_mod.AJUSTE_NEGATIVO


def test_feedback_ao_vivo_sem_genero_resolvido_ainda_registra_feedback():
    entrada = feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorSemGenero(), "Faixa X", "Artista Y", "positivo")
    assert entrada is not None
    assert entrada["user_feedback"] == "positivo"


def test_feedback_ao_vivo_provedor_indisponivel_ainda_registra_feedback():
    entrada = feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorQuebrado(), "Faixa X", "Artista Y", "positivo")
    assert entrada is not None
    assert entrada["user_feedback"] == "positivo"


def test_feedback_ao_vivo_segunda_vez_atualiza_entrada_existente():
    provedor = _ProvedorFalso()
    feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Doomsday", "MF DOOM", "positivo")
    feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Doomsday", "MF DOOM", "negativo")

    historico = historico_mod.obter_historico(USUARIO)
    entradas_doomsday = [e for e in historico if e["titulo"] == "Doomsday"]
    assert len(entradas_doomsday) == 1
    assert entradas_doomsday[0]["user_feedback"] == "negativo"


def test_feedback_ao_vivo_isolado_por_pessoa():
    outro_usuario = "222222"
    provedor = _ProvedorFalso()
    feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Doomsday", "MF DOOM", "positivo")
    assert historico_mod.obter_historico(outro_usuario) == []


def test_feedback_ao_vivo_negativo_remove_so_a_faixa_exata_do_pool():
    """Pedido do usuário 2026-08-27: "um 👎 em 1 musica n pode condenar
    todas desse artista. Assim como o like n aprova todas tbm, algumas eu
    gosto e outras nao" - negativo é simétrico ao positivo, só a faixa
    exata sai, o resto do mesmo artista fica no pool."""
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato_ranqueado("Doomsday", "MF DOOM", ["boom bap"], 0.7),
        _candidato_ranqueado("Rhymes Like Dimes", "MF DOOM", ["boom bap"], 0.6),
    ])
    feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorFalso(), "Doomsday", "MF DOOM", "negativo")

    pool = pool_mod.carregar_pool(USUARIO)
    assert {c["titulo"] for c in pool} == {"Rhymes Like Dimes"}


def test_feedback_ao_vivo_positivo_remove_so_a_faixa_exata_do_pool():
    """Pedido do usuário 2026-08-26: "Musicas sem voto não saem do pool" -
    votada (positivo aqui) sai, mas só ELA - resto do mesmo artista fica."""
    pool_mod.gerar_pool_incremental(USUARIO, [
        _candidato_ranqueado("Doomsday", "MF DOOM", ["boom bap"], 0.7),
        _candidato_ranqueado("Rhymes Like Dimes", "MF DOOM", ["boom bap"], 0.6),
    ])
    feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorFalso(), "Doomsday", "MF DOOM", "positivo")

    pool = pool_mod.carregar_pool(USUARIO)
    assert {c["titulo"] for c in pool} == {"Rhymes Like Dimes"}


def test_processar_feedback_remove_a_faixa_votada_do_pool():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="compatibilidade", category="compatibilidade")
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato_ranqueado("Song A", "Artista A", ["pop"], 0.5)])
    track_id = historico_mod.track_id("Song A", "Artista A")

    feedback_mod.processar_feedback(USUARIO, track_id, "positivo", genero="pop")

    assert pool_mod.carregar_pool(USUARIO) == []


# --- Feedback passivo (fraco/acumulativo) ---

def test_feedback_passivo_sempre_registra_evento_mesmo_sem_ajustar_peso():
    """Fração no meio-termo (nem claramente pulada cedo, nem ouvida quase
    inteira) não conta como sinal em NENHUMA direção - mas o evento bruto
    ainda é logado (histórico separado), só não muda o peso."""
    resultado = feedback_mod.processar_feedback_passivo(
        USUARIO, _ProvedorFalso(), "Song A", "Artista A", fracao_tocada=0.5, pulado=True, momento_do_skip=15,
    )
    assert resultado == {"ajustou_peso": False}
    assert historico_mod.contar_eventos_fracos_recentes(USUARIO, "Artista A", negativo=True) == 0
    assert historico_mod.contar_eventos_fracos_recentes(USUARIO, "Artista A", negativo=False) == 0


def test_feedback_passivo_isolado_nao_ajusta_peso():
    provedor = _ProvedorFalso(generos_por_artista={"artista a": ["pop"]})
    resultado = feedback_mod.processar_feedback_passivo(
        USUARIO, provedor, "Song A", "Artista A", fracao_tocada=0.1, pulado=True, momento_do_skip=3,
    )
    assert resultado == {"ajustou_peso": False}


def test_feedback_passivo_acumula_ate_ajustar_peso():
    provedor = _ProvedorFalso(generos_por_artista={"artista a": ["pop"]})
    perfil_mod.definir_peso_genero(USUARIO, "pop", 0.5)

    for i in range(feedback_mod.MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR - 1):
        resultado = feedback_mod.processar_feedback_passivo(
            USUARIO, provedor, f"Song {i}", "Artista A", fracao_tocada=0.1, pulado=True, momento_do_skip=3,
        )
        assert resultado == {"ajustou_peso": False}

    resultado_final = feedback_mod.processar_feedback_passivo(
        USUARIO, provedor, "Song Final", "Artista A", fracao_tocada=0.1, pulado=True, momento_do_skip=3,
    )
    assert resultado_final == {"ajustou_peso": True, "negativo": True}

    perfil_depois = perfil_mod.carregar_perfil(USUARIO)
    assert perfil_depois["preferred_genres"]["pop"] == 0.5 + feedback_mod.AJUSTE_PASSIVO_NEGATIVO


def test_feedback_passivo_positivo_acumula_ate_ajustar_peso():
    provedor = _ProvedorFalso(generos_por_artista={"artista a": ["pop"]})
    perfil_mod.definir_peso_genero(USUARIO, "pop", 0.5)

    for i in range(feedback_mod.MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR):
        resultado = feedback_mod.processar_feedback_passivo(
            USUARIO, provedor, f"Song {i}", "Artista A", fracao_tocada=0.95, pulado=False,
        )

    assert resultado == {"ajustou_peso": True, "negativo": False}
    perfil_depois = perfil_mod.carregar_perfil(USUARIO)
    assert perfil_depois["preferred_genres"]["pop"] == 0.5 + feedback_mod.AJUSTE_PASSIVO_POSITIVO


def test_feedback_passivo_fracao_no_meio_termo_nao_conta_em_nenhuma_direcao():
    resultado = feedback_mod.processar_feedback_passivo(
        USUARIO, _ProvedorFalso(), "Song A", "Artista A", fracao_tocada=0.5, pulado=True, momento_do_skip=30,
    )
    assert resultado == {"ajustou_peso": False}


def test_feedback_passivo_sem_genero_resolvido_nao_ajusta_mesmo_com_padrao():
    provedor = _ProvedorSemGenero()
    for i in range(feedback_mod.MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR):
        resultado = feedback_mod.processar_feedback_passivo(
            USUARIO, provedor, f"Song {i}", "Artista A", fracao_tocada=0.1, pulado=True, momento_do_skip=3,
        )
    assert resultado == {"ajustou_peso": False}

# -*- coding: utf-8 -*-
from echo.core import feedback as feedback_mod
from echo.core import historico as historico_mod
from echo.core import perfil as perfil_mod
from echo.providers import ProvedorIndisponivel


class _ProvedorFalso:
    def __init__(self, generos_por_artista=None):
        self._generos_por_artista = generos_por_artista or {}

    def resolver_generos(self, nomes_artistas):
        return {n.lower(): self._generos_por_artista.get(n.lower(), []) for n in nomes_artistas}


def test_feedback_ao_vivo_cria_entrada_quando_faixa_nunca_foi_recomendada():
    """Botão de like/dislike no Modo Música do ERIS - a faixa tocada pode nunca
    ter passado pelo Radar (busca livre do usuário)."""
    provedor = _ProvedorFalso()
    entrada = feedback_mod.processar_feedback_ao_vivo(provedor, "Doomsday", "MF DOOM", "positivo")

    assert entrada is not None
    assert entrada["user_feedback"] == "positivo"
    assert entrada["reason"] == "modo_musica"

    historico = historico_mod.obter_historico()
    assert historico[0]["titulo"] == "Doomsday"


def test_feedback_ao_vivo_ajusta_peso_do_genero_resolvido():
    provedor = _ProvedorFalso(generos_por_artista={"mf doom": ["boom bap"]})
    perfil_antes = perfil_mod.carregar_perfil()
    assert "boom bap" not in perfil_antes["preferred_genres"]

    feedback_mod.processar_feedback_ao_vivo(provedor, "Doomsday", "MF DOOM", "positivo")

    perfil_depois = perfil_mod.carregar_perfil()
    assert perfil_depois["preferred_genres"]["boom bap"] == feedback_mod.AJUSTE_POSITIVO + 0.5


def test_feedback_ao_vivo_negativo_reduz_peso():
    provedor = _ProvedorFalso(generos_por_artista={"mf doom": ["boom bap"]})
    perfil_mod.definir_peso_genero("boom bap", 0.5)

    feedback_mod.processar_feedback_ao_vivo(provedor, "Doomsday", "MF DOOM", "negativo")

    perfil_depois = perfil_mod.carregar_perfil()
    assert perfil_depois["preferred_genres"]["boom bap"] == 0.5 + feedback_mod.AJUSTE_NEGATIVO


def test_feedback_ao_vivo_sem_genero_resolvido_ainda_registra_feedback():
    class _ProvedorSemGenero:
        def resolver_generos(self, nomes_artistas):
            return {n.lower(): [] for n in nomes_artistas}

    entrada = feedback_mod.processar_feedback_ao_vivo(_ProvedorSemGenero(), "Faixa X", "Artista Y", "positivo")
    assert entrada is not None
    assert entrada["user_feedback"] == "positivo"


def test_feedback_ao_vivo_provedor_indisponivel_ainda_registra_feedback():
    class _ProvedorQuebrado:
        def resolver_generos(self, nomes_artistas):
            raise ProvedorIndisponivel("sem credencial")

    entrada = feedback_mod.processar_feedback_ao_vivo(_ProvedorQuebrado(), "Faixa X", "Artista Y", "positivo")
    assert entrada is not None
    assert entrada["user_feedback"] == "positivo"


def test_feedback_ao_vivo_segunda_vez_atualiza_entrada_existente():
    provedor = _ProvedorFalso()
    feedback_mod.processar_feedback_ao_vivo(provedor, "Doomsday", "MF DOOM", "positivo")
    feedback_mod.processar_feedback_ao_vivo(provedor, "Doomsday", "MF DOOM", "negativo")

    historico = historico_mod.obter_historico()
    entradas_doomsday = [e for e in historico if e["titulo"] == "Doomsday"]
    assert len(entradas_doomsday) == 1
    assert entradas_doomsday[0]["user_feedback"] == "negativo"

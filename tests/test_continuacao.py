# -*- coding: utf-8 -*-
from echo.core import perfil as perfil_mod
from echo.core import continuacao as continuacao_mod
from echo.providers import ProvedorIndisponivel


class _ProvedorFalso:
    """Dublê de teste - nunca faz chamada de rede, só devolve dados fixos
    configurados por cada teste."""

    def __init__(self, generos_por_artista=None, faixas_do_artista=None, faixas_por_tag=None):
        self._generos_por_artista = generos_por_artista or {}
        self._faixas_do_artista = faixas_do_artista or {}
        self._faixas_por_tag = faixas_por_tag or {}

    def resolver_generos(self, nomes_artistas):
        return {n.lower(): self._generos_por_artista.get(n.lower(), []) for n in nomes_artistas}

    def obter_faixas_do_artista(self, nome, limite=10):
        return self._faixas_do_artista.get(nome.lower(), [])

    def obter_faixas_por_tag(self, tag, limite=10):
        return self._faixas_por_tag.get(tag.lower(), [])


def _faixa(titulo, artista, generos, popularidade=50):
    return {"titulo": titulo, "artista": artista, "generos": generos, "popularidade": popularidade}


def test_sugere_proxima_do_mesmo_artista():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Doomsday", "MF DOOM", ["boom bap"], 70)]},
    )
    perfil = perfil_mod.carregar_perfil()
    proxima = continuacao_mod.sugerir_proxima(provedor, perfil, "MF DOOM", "Rapp Snitch Knishes")
    assert proxima is not None
    assert proxima["titulo"] == "Doomsday"


def test_nunca_sugere_a_propria_faixa_atual():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Doomsday", "MF DOOM", ["boom bap"], 70)]},
    )
    perfil = perfil_mod.carregar_perfil()
    proxima = continuacao_mod.sugerir_proxima(provedor, perfil, "MF DOOM", "Doomsday")
    assert proxima is None


def test_respeita_exclusao_de_sessao():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Doomsday", "MF DOOM", ["boom bap"], 70)]},
    )
    perfil = perfil_mod.carregar_perfil()
    proxima = continuacao_mod.sugerir_proxima(
        provedor, perfil, "MF DOOM", "Rapp Snitch Knishes", excluidos=["mf doom::doomsday"],
    )
    assert proxima is None


def test_none_quando_provedor_indisponivel_em_tudo():
    class _ProvedorQuebrado:
        def resolver_generos(self, nomes_artistas):
            raise ProvedorIndisponivel("sem credencial")

        def obter_faixas_do_artista(self, nome, limite=10):
            raise ProvedorIndisponivel("sem credencial")

        def obter_faixas_por_tag(self, tag, limite=10):
            raise ProvedorIndisponivel("sem credencial")

    perfil = perfil_mod.carregar_perfil()
    proxima = continuacao_mod.sugerir_proxima(_ProvedorQuebrado(), perfil, "MF DOOM", "Doomsday")
    assert proxima is None


def test_prioriza_genero_da_semente_sobre_candidato_de_tag_incompativel():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Rhymes Like Dimes", "MF DOOM", ["boom bap"], 60)]},
        faixas_por_tag={"boom bap": [_faixa("Outra Boom Bap", "Artista Y", ["boom bap"], 90)]},
    )
    perfil = perfil_mod.carregar_perfil()
    proxima = continuacao_mod.sugerir_proxima(provedor, perfil, "MF DOOM", "Doomsday")
    assert proxima is not None
    assert proxima["generos"] == ["boom bap"]


def _perfil_vazio():
    return {
        "favorite_artists": [], "disliked_artists": [], "liked_tracks": [], "disliked_tracks": [],
        "preferred_genres": {}, "preferred_eras": {}, "discovery_level": 0.5,
    }


def test_sugere_semente_funciona_com_perfil_totalmente_vazio():
    """`/caos` (ERIS) precisa funcionar mesmo sem artista/gênero cadastrado -
    o chart global sozinho (relevância + exploração) já basta."""
    candidatos = [_faixa("Trending Now", "Artista Global", ["pop"], 80)]
    semente = continuacao_mod.sugerir_semente(candidatos, _perfil_vazio())
    assert semente is not None
    assert semente["titulo"] == "Trending Now"


def test_sugere_semente_prefere_artista_favorito_do_perfil():
    perfil = _perfil_vazio()
    perfil["favorite_artists"] = [{"nome": "MF DOOM", "genero": "boom bap"}]
    perfil["preferred_genres"] = {"boom bap": 0.9}
    candidatos = [
        _faixa("Trending Now", "Artista Global", ["pop"], 80),
        _faixa("Doomsday", "MF DOOM", ["boom bap"], 40),
    ]
    semente = continuacao_mod.sugerir_semente(candidatos, perfil)
    assert semente is not None
    assert semente["titulo"] == "Doomsday"


def test_sugere_semente_sem_candidato_devolve_none():
    assert continuacao_mod.sugerir_semente([], _perfil_vazio()) is None


def test_sugere_semente_respeita_exclusao_de_sessao():
    candidatos = [_faixa("Trending Now", "Artista Global", ["pop"], 80)]
    semente = continuacao_mod.sugerir_semente(
        candidatos, _perfil_vazio(), excluidos=["artista global::trending now"],
    )
    assert semente is None

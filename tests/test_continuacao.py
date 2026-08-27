# -*- coding: utf-8 -*-
"""🔥 Reescrito (2026-08-26) pro `continuacao.py` pool-based: cadeia de fallback
em camadas por pessoa - pool pessoal → aprovadas dessa pessoa → descoberta
emergencial síncrona (rede, só quando as duas primeiras falharem)."""
from echo.core import perfil as perfil_mod
from echo.core import historico as historico_mod
from echo.core import pool as pool_mod
from echo.core import continuacao as continuacao_mod
from echo.providers import ProvedorIndisponivel

USUARIO = "111111"


class _ProvedorFalso:
    """Dublê de teste - nunca faz chamada de rede, só devolve dados fixos
    configurados por cada teste."""

    def __init__(self, generos_por_artista=None, faixas_do_artista=None, faixas_por_tag=None, lancamentos_novos=None):
        self._generos_por_artista = generos_por_artista or {}
        self._faixas_do_artista = faixas_do_artista or {}
        self._faixas_por_tag = faixas_por_tag or {}
        self._lancamentos_novos = lancamentos_novos or []

    def resolver_generos(self, nomes_artistas):
        return {n.lower(): self._generos_por_artista.get(n.lower(), []) for n in nomes_artistas}

    def obter_faixas_do_artista(self, nome, limite=10):
        return self._faixas_do_artista.get(nome.lower(), [])

    def obter_faixas_por_tag(self, tag, limite=10):
        return self._faixas_por_tag.get(tag.lower(), [])

    def obter_lancamentos_novos(self, limite=15):
        return self._lancamentos_novos


class _ProvedorQuebrado:
    def resolver_generos(self, nomes_artistas):
        raise ProvedorIndisponivel("sem credencial")

    def obter_faixas_do_artista(self, nome, limite=10):
        raise ProvedorIndisponivel("sem credencial")

    def obter_faixas_por_tag(self, tag, limite=10):
        raise ProvedorIndisponivel("sem credencial")

    def obter_lancamentos_novos(self, limite=15):
        raise ProvedorIndisponivel("sem credencial")


def _faixa(titulo, artista, generos, popularidade=50):
    return {"titulo": titulo, "artista": artista, "generos": generos, "popularidade": popularidade}


def _candidato_ranqueado(titulo, artista, generos, score, categoria="compatibilidade"):
    return {"titulo": titulo, "artista": artista, "generos": generos, "_score": score, "_categoria": categoria}


# --- Camada 1: pool pessoal (sem rede) ---

def test_sugere_proxima_consome_do_pool_sem_tocar_provedor():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato_ranqueado("Doomsday", "MF DOOM", ["boom bap"], 0.8)])
    proxima = continuacao_mod.sugerir_proxima(USUARIO, _ProvedorQuebrado(), "Outro Artista", "Outra Musica")
    assert proxima is not None
    assert proxima["titulo"] == "Doomsday"


def test_sugere_semente_consome_do_pool_sem_tocar_provedor():
    pool_mod.gerar_pool_incremental(USUARIO, [_candidato_ranqueado("Trending Now", "Artista Global", ["pop"], 0.6)])
    semente = continuacao_mod.sugerir_semente(USUARIO, _ProvedorQuebrado())
    assert semente is not None
    assert semente["titulo"] == "Trending Now"


# --- Camada 2: aprovadas dessa pessoa ---

def test_sugere_proxima_cai_pras_aprovadas_quando_pool_vazio():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "positivo")
    proxima = continuacao_mod.sugerir_proxima(USUARIO, _ProvedorQuebrado(), "Outro Artista", "Outra Musica")
    assert proxima is not None
    assert proxima["titulo"] == "Song A"


def test_sugere_semente_cai_pras_aprovadas_quando_pool_vazio():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "positivo")
    semente = continuacao_mod.sugerir_semente(USUARIO, _ProvedorQuebrado())
    assert semente is not None
    assert semente["titulo"] == "Song A"


def test_aprovadas_respeitam_exclusao_de_sessao():
    historico_mod.registrar_recomendacao(USUARIO, "Song A", "Artista A", reason="pool", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Song A", "Artista A"), "positivo")
    proxima = continuacao_mod.sugerir_proxima(
        USUARIO, _ProvedorQuebrado(), "Outro Artista", "Outra Musica", excluidos=["artista a::song a"],
    )
    assert proxima is None


# --- Camada 3: descoberta emergencial síncrona (pool e aprovadas vazios) ---

def test_sugere_proxima_do_mesmo_artista_via_descoberta_emergencial():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Doomsday", "MF DOOM", ["boom bap"], 70)]},
    )
    proxima = continuacao_mod.sugerir_proxima(USUARIO, provedor, "MF DOOM", "Rapp Snitch Knishes")
    assert proxima is not None
    assert proxima["titulo"] == "Doomsday"


def test_nunca_sugere_a_propria_faixa_atual():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Doomsday", "MF DOOM", ["boom bap"], 70)]},
    )
    proxima = continuacao_mod.sugerir_proxima(USUARIO, provedor, "MF DOOM", "Doomsday")
    assert proxima is None


def test_none_quando_provedor_indisponivel_em_tudo():
    proxima = continuacao_mod.sugerir_proxima(USUARIO, _ProvedorQuebrado(), "MF DOOM", "Doomsday")
    assert proxima is None


def test_prioriza_genero_da_semente_sobre_candidato_de_tag_incompativel():
    provedor = _ProvedorFalso(
        generos_por_artista={"mf doom": ["boom bap"]},
        faixas_do_artista={"mf doom": [_faixa("Rhymes Like Dimes", "MF DOOM", ["boom bap"], 60)]},
        faixas_por_tag={"boom bap": [_faixa("Outra Boom Bap", "Artista Y", ["boom bap"], 90)]},
    )
    proxima = continuacao_mod.sugerir_proxima(USUARIO, provedor, "MF DOOM", "Doomsday")
    assert proxima is not None
    assert proxima["generos"] == ["boom bap"]


def test_sugere_semente_funciona_com_perfil_totalmente_vazio():
    """`/caos` (ERIS) precisa funcionar mesmo sem artista/gênero cadastrado nem
    pool/aprovadas ainda gerados - o chart global sozinho já basta."""
    provedor = _ProvedorFalso(lancamentos_novos=[_faixa("Trending Now", "Artista Global", ["pop"], 80)])
    semente = continuacao_mod.sugerir_semente(USUARIO, provedor)
    assert semente is not None
    assert semente["titulo"] == "Trending Now"


def test_sugere_semente_prefere_artista_favorito_do_perfil():
    perfil_mod.adicionar_artista_favorito(USUARIO, "MF DOOM", genero="boom bap")
    perfil_mod.definir_peso_genero(USUARIO, "boom bap", 0.9)
    provedor = _ProvedorFalso(lancamentos_novos=[
        _faixa("Trending Now", "Artista Global", ["pop"], 80),
        _faixa("Doomsday", "MF DOOM", ["boom bap"], 40),
    ])
    semente = continuacao_mod.sugerir_semente(USUARIO, provedor)
    assert semente is not None
    assert semente["titulo"] == "Doomsday"


def test_sugere_semente_sem_candidato_devolve_none():
    assert continuacao_mod.sugerir_semente(USUARIO, _ProvedorFalso()) is None


def test_sugere_semente_sem_provedor_devolve_none():
    assert continuacao_mod.sugerir_semente(USUARIO) is None


def test_sugere_semente_respeita_exclusao_de_sessao():
    provedor = _ProvedorFalso(lancamentos_novos=[_faixa("Trending Now", "Artista Global", ["pop"], 80)])
    semente = continuacao_mod.sugerir_semente(USUARIO, provedor, excluidos=["artista global::trending now"])
    assert semente is None

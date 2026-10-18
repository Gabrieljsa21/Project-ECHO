# -*- coding: utf-8 -*-
"""Nightcore/AMV trocados pela versão oficial (2026-10-17)."""
import pytest

from echo.core import artistas as artistas_mod
from echo.core import feedback as feedback_mod
from echo.core import pool as pool_mod
from echo.core import versoes as versoes_mod

USUARIO = "111111"

BUSCA = {
    "black betty": [
        {"titulo": "black betty", "artista": "Black Lagoon AMV", "ouvintes": "40"},
        {"titulo": "Black Betty", "artista": "Ram Jam", "ouvintes": "840539"},
    ],
    "move thousand foot krutch": [
        {"titulo": "Courtesy Call", "artista": "Thousand Foot Krutch", "ouvintes": "352878"},
        {"titulo": "Move", "artista": "Thousand Foot Krutch", "ouvintes": "229765"},
    ],
    "itachi vs. sasuke": [
        {"titulo": "Itachi VS. Sasuke", "artista": "Naruto", "ouvintes": "110"},
    ],
    "random road trip": [
        {"titulo": "Road Trip", "artista": "NCT 127", "ouvintes": "56930"},
    ],
}


class _ProvedorFalso:
    def __init__(self, top_por_artista=None):
        self._top = top_por_artista or {}
        self.buscas = []

    def buscar_faixa(self, query, resolver_generos=True):
        self.buscas.append(query)
        return [dict(r) for r in BUSCA.get(query.lower(), [])]

    def resolver_generos(self, nomes_artistas):
        return {n.lower(): ["rock"] for n in nomes_artistas}

    def obter_faixas_do_artista(self, nome, limite=10):
        return [{"titulo": t, "artista": nome, "generos": []} for t in self._top.get(nome.lower(), [])][:limite]


@pytest.mark.parametrize("artista, titulo", [
    ("PluggedToNightcore", "Last Christmas"),
    ("VermillionAMV", "Ardent Sky"),
    ("Jasi Amvs", "Qualquer"),
    ("thebestamvsofalltime", "Nightmare"),
    ("CLuBLioNx", "╭Nightstyle╯Nightcore - Dance Till You're Dead"),
    ("akailidium", "Thou Shall Not Kill AMV \\\\ Btooom!"),
    ("Alguém", "Song (sped up)"),
])
def test_reconhece_versao_derivada(artista, titulo):
    assert versoes_mod.eh_derivada(artista, titulo)


@pytest.mark.parametrize("artista, titulo", [
    ("Ram Jam", "Black Betty"),
    ("Fall Out Boy", "Centuries"),
    ("Thousand Foot Krutch", "Move (Remix)"),
])
def test_musica_oficial_nao_e_derivada(artista, titulo):
    assert not versoes_mod.eh_derivada(artista, titulo)


@pytest.mark.parametrize("titulo, artista, esperado", [
    ("「Nightcore」→ Please Don't Go", "ღ NightcoreGalaxy ღ", "Please Don't Go"),
    ("[Nightcore] You're Gonna Go Far Kid", "PluggedToNightcore", "You're Gonna Go Far Kid"),
    ("Nightcore - Sleep When We're Dead [Italobrothers] ▹Lyrics◃", "CLuBLioNx", "Sleep When We're Dead"),
    ("The Boy Who Murdered Love - Bestamvsofalltime Anime MV ♫", "amv", "The Boy Who Murdered Love"),
    ("Move - Thousand foot krutch", "BLEACH AMV", "Move Thousand foot krutch"),
])
def test_titulo_limpo(titulo, artista, esperado):
    assert versoes_mod.titulo_limpo(titulo, artista) == esperado


def test_acha_a_oficial_pelo_titulo():
    oficial = versoes_mod.buscar_oficial(_ProvedorFalso(), "Black Lagoon AMV", "black betty")
    assert (oficial["artista"], oficial["titulo"]) == ("Ram Jam", "Black Betty")
    assert oficial["generos"] == ["rock"]


def test_titulo_com_nome_do_artista_acha_a_musica_certa():
    oficial = versoes_mod.buscar_oficial(_ProvedorFalso(), "BLEACH AMV", "Move - Thousand foot krutch")
    assert (oficial["artista"], oficial["titulo"]) == ("Thousand Foot Krutch", "Move")


def test_sem_oficial_confiavel_devolve_none():
    provedor = _ProvedorFalso()
    assert versoes_mod.buscar_oficial(provedor, "naruto amv", "Itachi VS. Sasuke") is None
    assert versoes_mod.buscar_oficial(provedor, "amv", "[MEP] Random Road Trip 720p") is None


def test_oficializar_troca_derivada_e_descarta_sem_oficial():
    candidatos = [
        {"titulo": "Centuries", "artista": "Fall Out Boy", "fonte": "artista_favorito"},
        {"titulo": "black betty", "artista": "Black Lagoon AMV", "fonte": "artista_favorito"},
        {"titulo": "Itachi VS. Sasuke", "artista": "naruto amv", "fonte": "artista_favorito"},
    ]
    resultado = versoes_mod.oficializar(_ProvedorFalso(), candidatos)
    assert [(c["artista"], c["titulo"], c["fonte"]) for c in resultado] == [
        ("Fall Out Boy", "Centuries", "artista_favorito"),
        ("Ram Jam", "Black Betty", "artista_favorito"),
    ]


def test_oficial_ja_votada_nao_volta():
    feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorFalso(), "Black Betty", "Ram Jam", "negativo")
    candidatos = [{"titulo": "black betty", "artista": "Black Lagoon AMV"}]
    assert versoes_mod.oficializar(_ProvedorFalso(), candidatos, USUARIO) == []


def test_descurtir_canal_de_nightcore_nao_abre_prova():
    provedor = _ProvedorFalso({"pluggedtonightcore": ["Animals", "Last Christmas", "Shower"]})
    feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor, "Light Em Up Remix", "PluggedToNightcore", "negativo")
    registro = artistas_mod.carregar(USUARIO)["pluggedtonightcore"]
    assert registro["estado"] == artistas_mod.ESTADO_NORMAL
    assert registro["prova"] == []


def test_prova_antiga_de_canal_nao_e_mais_servida():
    artistas = artistas_mod.carregar(USUARIO)
    artistas["hd nightcore"] = {
        **artistas_mod._registro_vazio("HD Nightcore"),
        "estado": artistas_mod.ESTADO_EM_PROVA,
        "prova": [{"titulo": "God Is A Girl", "artista": "HD Nightcore", "vezes_servida": 0}],
    }
    todos = artistas_mod._carregar_todos()
    todos[USUARIO]["artistas"] = artistas
    artistas_mod._salvar_todos(todos)
    for _ in range(artistas_mod.INTERVALO_PROVA * 2):
        assert artistas_mod.proxima_faixa_de_prova(USUARIO) is None


def test_pool_nao_serve_derivada():
    pool_mod._salvar_pool(USUARIO, [
        {"titulo": "black betty", "artista": "Black Lagoon AMV", "generos": [], "afinidade": 0.9, "origem": "x"},
        {"titulo": "Centuries", "artista": "Fall Out Boy", "generos": [], "afinidade": 0.1, "origem": "x"},
    ])
    pool_mod.MINIMO_DISPONIVEL, minimo = 0, pool_mod.MINIMO_DISPONIVEL
    try:
        for _ in range(5):
            assert pool_mod.consumir_proxima(USUARIO)["artista"] == "Fall Out Boy"
    finally:
        pool_mod.MINIMO_DISPONIVEL = minimo


def test_reabastecimento_troca_derivadas_que_ja_estavam_no_pool(monkeypatch):
    pool_mod._salvar_pool(USUARIO, [
        {"titulo": "black betty", "artista": "Black Lagoon AMV", "generos": [], "afinidade": 0.7,
         "origem": "reabastecimento_aprovadas", "artista_semente": "Black Lagoon AMV", "descoberto_em": "2026-10-16"},
        {"titulo": "Itachi VS. Sasuke", "artista": "naruto amv", "generos": [], "afinidade": 0.6,
         "origem": "reabastecimento_aprovadas", "artista_semente": "naruto amv", "descoberto_em": "2026-10-16"},
    ])
    feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorFalso(), "Centuries", "Fall Out Boy", "positivo")
    monkeypatch.setattr(pool_mod, "obter_provedor", lambda: _ProvedorFalso())
    monkeypatch.setattr(pool_mod, "_artistas_para_buscar", lambda provedor, sementes: iter([]))
    pool_mod.reabastecer_pool(USUARIO)
    assert [(c["artista"], c["titulo"], c["afinidade"]) for c in pool_mod.carregar_pool(USUARIO)] == [
        ("Ram Jam", "Black Betty", 0.7),
    ]


def test_pista_entre_colchetes_desempata_o_artista():
    BUSCA["hero pegboard nerds"] = [{"titulo": "Hero", "artista": "Pegboard Nerds", "ouvintes": "90000"}]
    BUSCA["hero"] = [{"titulo": "Hero", "artista": "Skillet", "ouvintes": "900000"}]
    oficial = versoes_mod.buscar_oficial(
        _ProvedorFalso(), "CLuBLioNx", "Nightstyle - Hero (Da Tweekaz 'Guitar Hero' Mix) [Pegboard Nerds]",
    )
    assert oficial["artista"] == "Pegboard Nerds"

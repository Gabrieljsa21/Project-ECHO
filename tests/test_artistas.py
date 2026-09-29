# -*- coding: utf-8 -*-
"""Pontuação por artista e regra das 5 chances (2026-09-26)."""
from echo.core import artistas as artistas_mod
from echo.core import continuacao as continuacao_mod
from echo.core import feedback as feedback_mod
from echo.core import historico as historico_mod
from echo.core import perfil as perfil_mod
from echo.core import pool as pool_mod
from echo.core import recomendador as recomendador_mod

USUARIO = "111111"


class _ProvedorFalso:
    def __init__(self, top_por_artista=None):
        self._top = top_por_artista or {}

    def resolver_generos(self, nomes_artistas):
        return {n.lower(): [] for n in nomes_artistas}

    def obter_faixas_do_artista(self, nome, limite=10):
        return [{"titulo": t, "artista": nome, "generos": []} for t in self._top.get(nome.lower(), [])][:limite]

    def obter_faixas_por_tag(self, tag, limite=10):
        return []

    def obter_lancamentos_novos(self, limite=15):
        return []


TOP_BANDA = ["Hit 1", "Hit 2", "Hit 3", "Hit 4", "Hit 5", "Hit 6"]


def _votar(titulo, artista, feedback, provedor=None):
    return feedback_mod.processar_feedback_ao_vivo(USUARIO, provedor or _ProvedorFalso({"banda": TOP_BANDA}), titulo, artista, feedback)


def _registro(artista="Banda"):
    return artistas_mod.carregar(USUARIO)[artista.lower()]


def test_curtida_sobe_nota_com_retorno_decrescente():
    _votar("A", "Banda", "positivo")
    primeira = _registro()["nota"]
    _votar("B", "Banda", "positivo")
    segunda = _registro()["nota"]
    assert primeira == 0.25
    assert 0.25 < segunda < 0.5
    assert segunda - primeira < primeira


def test_descurtida_de_artista_sem_curtidas_abre_prova_com_as_5_mais_populares():
    _votar("Musica ruim", "Banda", "negativo")
    registro = _registro()
    assert registro["estado"] == artistas_mod.ESTADO_EM_PROVA
    assert [f["titulo"] for f in registro["prova"]] == TOP_BANDA[:5]
    assert registro["nota"] < 0


def test_descurtida_de_artista_com_curtida_so_desce_a_nota():
    _votar("Boa", "Banda", "positivo")
    _votar("Ruim", "Banda", "negativo")
    registro = _registro()
    assert registro["estado"] == artistas_mod.ESTADO_NORMAL
    assert registro["prova"] == []


def test_favorito_cadastrado_nao_entra_em_prova():
    perfil_mod.adicionar_artista_favorito(USUARIO, "Banda")
    _votar("Ruim", "Banda", "negativo")
    assert _registro()["estado"] == artistas_mod.ESTADO_NORMAL


def test_descurtir_as_5_da_prova_rejeita_o_artista():
    _votar("Musica ruim", "Banda", "negativo")
    for titulo in TOP_BANDA[:4]:
        _votar(titulo, "Banda", "negativo")
        assert _registro()["estado"] == artistas_mod.ESTADO_EM_PROVA
    _votar(TOP_BANDA[4], "Banda", "negativo")
    registro = _registro()
    assert registro["estado"] == artistas_mod.ESTADO_REJEITADO
    assert registro["nota"] == -1.0
    assert artistas_mod.esta_rejeitado(USUARIO, "Banda")


def test_uma_curtida_durante_a_prova_salva_o_artista():
    _votar("Musica ruim", "Banda", "negativo")
    _votar(TOP_BANDA[0], "Banda", "negativo")
    _votar(TOP_BANDA[1], "Banda", "positivo")
    registro = _registro()
    assert registro["estado"] == artistas_mod.ESTADO_NORMAL
    assert registro["prova"] == []


def test_curtir_artista_rejeitado_devolve_ele_ao_normal():
    _votar("Musica ruim", "Banda", "negativo")
    for titulo in TOP_BANDA[:5]:
        _votar(titulo, "Banda", "negativo")
    _votar("Achada na busca", "Banda", "positivo")
    assert _registro()["estado"] == artistas_mod.ESTADO_NORMAL


def test_faixas_ja_descurtidas_contam_como_chance_gasta():
    for titulo in TOP_BANDA[:3]:
        historico_mod.registrar_recomendacao(USUARIO, titulo, "Banda", reason="teste", category=None)
        historico_mod.registrar_feedback(USUARIO, historico_mod.track_id(titulo, "Banda"), "negativo")
    artistas_mod.carregar(USUARIO)  # reconstrói do histórico sem abrir prova
    assert _registro()["estado"] == artistas_mod.ESTADO_NORMAL
    _votar("Outra ruim", "Banda", "negativo")
    registro = _registro()
    assert registro["estado"] == artistas_mod.ESTADO_EM_PROVA
    assert registro["reprovadas_na_prova"] == 3
    assert [f["titulo"] for f in registro["prova"]] == TOP_BANDA[3:5]


def test_importacao_sem_abrir_prova_so_mexe_na_nota():
    feedback_mod.processar_feedback_ao_vivo(USUARIO, _ProvedorFalso({"banda": TOP_BANDA}), "Ruim", "Banda", "negativo", abrir_prova=False)
    registro = _registro()
    assert registro["estado"] == artistas_mod.ESTADO_NORMAL
    assert registro["nota"] < 0


def test_notas_iniciais_vem_dos_votos_ja_existentes():
    historico_mod.registrar_recomendacao(USUARIO, "Boa", "Banda", reason="teste", category=None)
    historico_mod.registrar_feedback(USUARIO, historico_mod.track_id("Boa", "Banda"), "positivo")
    registro = _registro()
    assert registro["curtidas"] == 1
    assert registro["nota"] == 0.25


def test_faixa_de_prova_entra_a_cada_intervalo():
    _votar("Musica ruim", "Banda", "negativo")
    servidas = [artistas_mod.proxima_faixa_de_prova(USUARIO) for _ in range(artistas_mod.INTERVALO_PROVA * 2)]
    faixas = [s for s in servidas if s]
    assert len(faixas) == 2
    assert servidas[artistas_mod.INTERVALO_PROVA - 1]["artista"] == "Banda"
    assert all(s is None for s in servidas[:artistas_mod.INTERVALO_PROVA - 1])


def test_faixa_servida_o_maximo_sem_voto_encerra_a_prova_como_neutra():
    provedor = _ProvedorFalso({"banda": ["Unica"]})
    _votar("Musica ruim", "Banda", "negativo", provedor)
    assert _registro()["prova"][0]["titulo"] == "Unica"
    rodadas = artistas_mod.INTERVALO_PROVA * (artistas_mod.MAX_VEZES_SERVIDA + 1)
    for _ in range(rodadas):
        artistas_mod.proxima_faixa_de_prova(USUARIO)
    assert _registro()["estado"] == artistas_mod.ESTADO_NORMAL


def test_descurtida_da_faixa_servida_pela_ultima_vez_ainda_conta():
    provedor = _ProvedorFalso({"banda": ["Unica"]})
    _votar("Musica ruim", "Banda", "negativo", provedor)
    for _ in range(artistas_mod.INTERVALO_PROVA * artistas_mod.MAX_VEZES_SERVIDA):
        artistas_mod.proxima_faixa_de_prova(USUARIO)
    _votar("Unica", "Banda", "negativo", provedor)
    assert _registro()["estado"] == artistas_mod.ESTADO_REJEITADO


def test_continuacao_serve_faixa_de_prova_antes_do_pool():
    _votar("Musica ruim", "Banda", "negativo")
    pool_mod.gerar_pool_incremental(USUARIO, [
        {"titulo": "Do Pool", "artista": "Outra", "generos": [], "_score": 0.9, "_categoria": "compatibilidade"},
    ])
    provedor = _ProvedorFalso({"banda": TOP_BANDA})
    sugestoes = [continuacao_mod.sugerir_semente(USUARIO, provedor) for _ in range(artistas_mod.INTERVALO_PROVA)]
    assert sugestoes[-1]["artista"] == "Banda"
    assert sugestoes[0]["artista"] == "Outra"


def test_rejeitado_some_do_pool_e_do_ranking():
    _votar("Musica ruim", "Banda", "negativo")
    for titulo in TOP_BANDA[:5]:
        _votar(titulo, "Banda", "negativo")
    pool_mod.gerar_pool_incremental(USUARIO, [
        {"titulo": "Mais uma", "artista": "Banda", "generos": [], "_score": 0.99, "_categoria": "compatibilidade"},
    ])
    assert pool_mod.consumir_proxima(USUARIO) is None
    perfil = perfil_mod.carregar_perfil(USUARIO)
    assert recomendador_mod.ranquear(USUARIO, [{"titulo": "X", "artista": "Banda", "generos": [], "popularidade": 90}], perfil) == []


def test_nota_alta_puxa_o_artista_pra_frente_no_pool():
    for titulo in ("A", "B", "C"):
        _votar(titulo, "Querida", "positivo")
    pool_mod.gerar_pool_incremental(USUARIO, [
        {"titulo": "Da Querida", "artista": "Querida", "generos": [], "_score": 0.5, "_categoria": "compatibilidade"},
    ] + [
        {"titulo": f"Neutra {i}", "artista": f"Neutro {i}", "generos": [], "_score": 0.55, "_categoria": "compatibilidade"}
        for i in range(5)
    ])
    ordem = sorted(
        pool_mod.carregar_pool(USUARIO),
        key=lambda c: c["afinidade"] + pool_mod.PESO_NOTA_ARTISTA * artistas_mod.nota_efetiva(USUARIO, c["artista"]),
        reverse=True,
    )
    assert ordem[0]["artista"] == "Querida"


def test_detalhes_do_artista_traz_populares_e_nota():
    _votar("A", "Banda", "positivo")
    detalhes = artistas_mod.detalhes(USUARIO, _ProvedorFalso({"banda": TOP_BANDA}), "Banda", limite=3)
    assert [f["titulo"] for f in detalhes["populares"]] == TOP_BANDA[:3]
    assert detalhes["nota"] == 0.25
    assert detalhes["curtidas"] == 1
    assert detalhes["estado"] == artistas_mod.ESTADO_NORMAL


def test_detalhes_sem_provedor_ainda_traz_a_nota():
    class _Quebrado:
        def obter_faixas_do_artista(self, nome, limite=10):
            from echo.providers import ProvedorIndisponivel
            raise ProvedorIndisponivel("fora do ar")
    detalhes = artistas_mod.detalhes(USUARIO, _Quebrado(), "Ninguem")
    assert detalhes["populares"] == []
    assert detalhes["nota"] == 0.0

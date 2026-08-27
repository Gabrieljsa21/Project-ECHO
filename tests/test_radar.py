# -*- coding: utf-8 -*-
from echo.core import perfil as perfil_mod
from echo.core import radar as radar_mod

USUARIO = "111111"


def _candidato(titulo, artista, generos, popularidade=50):
    return {"titulo": titulo, "artista": artista, "generos": generos, "popularidade": popularidade}


def _perfil_boom_bap():
    perfil_mod.adicionar_artista_favorito(USUARIO, "MF DOOM", genero="boom bap")
    return perfil_mod.carregar_perfil(USUARIO)


def test_gerar_10_recomendacoes_com_candidatos_suficientes():
    _perfil_boom_bap()
    candidatos = [
        _candidato(f"Song {i}", f"Artista {i}", ["boom bap"], popularidade=60)
        for i in range(20)
    ]
    radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    assert len(radar) == 10


def test_trabalhar_com_menos_de_10_candidatos_validos():
    _perfil_boom_bap()
    candidatos = [_candidato(f"Song {i}", f"Artista {i}", ["boom bap"], popularidade=60) for i in range(3)]
    radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    assert len(radar) == 3


def test_impedir_duplicatas_entre_edicoes():
    _perfil_boom_bap()
    candidatos = [_candidato(f"Song {i}", f"Artista {i}", ["boom bap"], popularidade=60) for i in range(10)]
    primeiro_radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    ids_primeiro = {c["titulo"] for c in primeiro_radar}

    segundo_radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    ids_segundo = {c["titulo"] for c in segundo_radar}
    assert not (ids_primeiro & ids_segundo)


def test_limitar_mesmo_artista_a_uma_faixa_por_edicao():
    _perfil_boom_bap()
    candidatos = [_candidato(f"Song {i}", "Mesmo Artista", ["boom bap"], popularidade=60) for i in range(15)]
    radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    assert len(radar) <= 1


def test_nao_preencher_quota_com_candidato_de_score_baixo():
    perfil_mod.definir_peso_genero(USUARIO, "jazz experimental", 0.0)
    candidatos = [_candidato("Song ruim", "Artista Y", ["jazz experimental"], popularidade=None)]
    radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    assert radar == []


def test_respeitar_proporcoes_aproximadas_da_composicao():
    _perfil_boom_bap()
    candidatos = (
        [_candidato(f"Compat {i}", f"Fav Artista {i}", ["boom bap"], popularidade=70) for i in range(8)]
        + [_candidato(f"Alta {i}", f"Popular Artista {i}", ["pop"], popularidade=95) for i in range(8)]
    )
    radar = radar_mod.gerar_radar(USUARIO, candidatos, quantidade=10)
    categorias = [c["_categoria"] for c in radar]
    # com candidatos suficientes nas duas categorias, nenhuma delas deve dominar
    # sozinha o Radar inteiro (proporção aproximada, não exata - seção 7.3 do
    # ECHO_SPEC permite desvio quando falta candidato de qualidade numa categoria)
    assert 1 <= categorias.count("compatibilidade") < 10
    assert 1 <= categorias.count("relevancia") < 10
    assert len(radar) == 10


def test_radar_e_pool_isolados_por_pessoa():
    outro_usuario = "222222"
    perfil_mod.adicionar_artista_favorito(outro_usuario, "Taylor Swift", genero="pop")
    candidatos = [_candidato(f"Song {i}", f"Artista {i}", ["pop"], popularidade=60) for i in range(10)]
    radar_mod.gerar_radar(outro_usuario, candidatos, quantidade=5)

    assert radar_mod.obter_ultimo_radar(USUARIO) == []
    assert len(radar_mod.obter_ultimo_radar(outro_usuario)) == 5

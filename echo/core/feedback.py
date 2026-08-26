# -*- coding: utf-8 -*-
"""Processa feedback explícito (👍/👎) do Radar Musical (seções 12/21 do ECHO_SPEC) -
uma única ação faz um ajuste pequeno e incremental de peso de gênero, nunca substitui
o perfil nem bloqueia um artista sozinha (isso continua sendo uma ação manual
separada, `core.perfil.adicionar_artista_rejeitado`)."""
from echo.core import perfil as perfil_mod
from echo.core import historico as historico_mod
from echo.providers import ProvedorIndisponivel

AJUSTE_POSITIVO = 0.08
AJUSTE_NEGATIVO = -0.12


def processar_feedback(track_id, feedback, genero=None):
    """`genero` vem de quem está mandando o feedback (a GAIA reenvia o gênero
    dominante que recebeu junto com a faixa no Radar) - sem ele, o feedback ainda fica
    registrado no histórico, só não ajusta peso (não dá pra ajustar um gênero que não
    se sabe qual é)."""
    entrada = historico_mod.registrar_feedback(track_id, feedback)
    if entrada is None:
        return None

    if genero:
        perfil = perfil_mod.carregar_perfil()
        delta = AJUSTE_POSITIVO if feedback == "positivo" else AJUSTE_NEGATIVO
        perfil_mod.ajustar_peso_genero(perfil, genero, delta)
        perfil_mod.salvar_perfil(perfil)

    return entrada


def processar_feedback_ao_vivo(provedor, titulo, artista, feedback):
    """👍/👎 nos botões do Modo Música do ERIS (2026-08-26, pedido do usuário:
    "quando ela toca uma musica, podia aparecer botoes de like, dislike e
    next") - diferente do Radar, a faixa tocada ao vivo pode nunca ter
    passado por `historico.registrar_recomendacao` (veio de uma busca livre
    do usuário ou da continuação, não de uma edição fechada do Radar) - cria
    a entrada no histórico na hora se ela não existir, em vez de devolver
    None. O gênero não vem de quem chama (o ERIS não sabe gênero, só
    artista/título) - resolvido aqui mesmo via provedor, mesmo ajuste
    incremental do Radar (nunca substitui o perfil)."""
    track_id = historico_mod.track_id(titulo, artista)
    entrada = historico_mod.registrar_feedback(track_id, feedback)
    if entrada is None:
        historico_mod.registrar_recomendacao(titulo, artista, reason="modo_musica", category=None)
        entrada = historico_mod.registrar_feedback(track_id, feedback)

    try:
        generos = provedor.resolver_generos([artista]).get(artista.strip().lower(), [])
    except ProvedorIndisponivel:
        generos = []
    if generos:
        perfil = perfil_mod.carregar_perfil()
        delta = AJUSTE_POSITIVO if feedback == "positivo" else AJUSTE_NEGATIVO
        perfil_mod.ajustar_peso_genero(perfil, generos[0], delta)
        perfil_mod.salvar_perfil(perfil)

    return entrada

# -*- coding: utf-8 -*-
"""Processa feedback explícito (👍/👎) do Radar Musical (seções 12/21 do ECHO_SPEC) -
uma única ação faz um ajuste pequeno e incremental de peso de gênero, nunca substitui
o perfil nem bloqueia um artista sozinha (isso continua sendo uma ação manual
separada, `core.perfil.adicionar_artista_rejeitado`)."""
from echo.core import perfil as perfil_mod
from echo.core import historico as historico_mod

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

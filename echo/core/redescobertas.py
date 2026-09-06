# -*- coding: utf-8 -*-
"""Redescobertas (seção 9 do ECHO_SPEC) - recupera música que o usuário já
aprovou (👍) mas não aparece há muito tempo nem no Radar/pool/Modo Música nem
em escuta real, distinto de "evitar repetição" (seção 8, que é sobre não
repetir CEDO demais). Frequência baixa por design (seção 9: "para não
competir com o objetivo principal de descobrir músicas novas") - quem decide
QUANDO oferecer uma redescoberta é a GAIA (mesmo padrão do Radar semanal),
aqui só a seleção determinística de QUAL faixa oferecer.

TODO.md, Fase 2 do ECHO_SPEC: pendência resolvida aqui."""
from datetime import date

from echo.core import historico as historico_mod

DIAS_MINIMOS_SEM_APARECER = 180
QUANTIDADE_PADRAO = 1


def obter_redescobertas(discord_user_id, quantidade=QUANTIDADE_PADRAO, dias_minimos=DIAS_MINIMOS_SEM_APARECER):
    """Entre as faixas aprovadas (👍) dessa pessoa, as que não aparecem há
    pelo menos `dias_minimos` - a mais "esquecida" primeiro (maior tempo
    parada). `quantidade` baixa por padrão (seção 9: frequência deve ser
    baixa) - quem chama decide a cadência de oferecer isso. Faixa aprovada
    sem nenhuma aparição datável (não deveria acontecer - toda aprovação
    nasce de uma recomendação já registrada) fica de fora, nunca vira uma
    redescoberta "inventada"."""
    hoje = date.today()
    candidatas = []
    for aprovada in historico_mod.obter_aprovadas(discord_user_id):
        ultima_aparicao = historico_mod.obter_ultima_aparicao(discord_user_id, aprovada["track_id"])
        if ultima_aparicao is None:
            continue
        dias_sem_aparecer = (hoje - ultima_aparicao).days
        if dias_sem_aparecer >= dias_minimos:
            candidatas.append({**aprovada, "dias_sem_aparecer": dias_sem_aparecer})

    candidatas.sort(key=lambda c: c["dias_sem_aparecer"], reverse=True)
    return candidatas[:quantidade]

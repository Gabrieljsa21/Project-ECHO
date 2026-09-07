# -*- coding: utf-8 -*-
"""Em Alta (seção 3.3 do ECHO_SPEC) - músicas atualmente relevantes/populares,
mesmo quando não combinam perfeitamente com o perfil do usuário. Diferente do
Radar Musical semanal (edição fechada, composição fixa entre categorias): Em
Alta é consultado sob demanda e olha só popularidade atual, sem pesar
compatibilidade - reaproveita a MESMA fonte que o Radar já usa pra
"relevância" (`provedor.obter_lancamentos_novos`, ver `providers/lastfm.py`),
só numa apresentação separada (docs/TODO.md, Fase 2 do ECHO_SPEC - pendência
resolvida aqui).

Compartilha o dedup de 90 dias do Radar (`historico.foi_recomendada_
recentemente`) - uma faixa já mostrada recentemente em QUALQUER seção (Radar
ou Em Alta) não repete só porque continua popular (seção 8)."""
from echo.core import historico as historico_mod

QUANTIDADE_PADRAO = 10


def obter_em_alta(discord_user_id, candidatos, quantidade=QUANTIDADE_PADRAO):
    """`candidatos` já vem do provedor (mesma coleta do Radar,
    `obter_lancamentos_novos`) - só filtra dedup e ordena por popularidade,
    sem pesar compatibilidade (é sobre o que tá tocando AGORA, não sobre o
    gosto de quem pergunta). Máx. 1 faixa por artista (mesma regra de
    diversidade do Radar, seção 20). Nunca inventa popularidade: candidato
    sem valor informado pelo provedor fica no fim, nunca no topo."""
    elegiveis = [
        c for c in candidatos
        if not historico_mod.foi_recomendada_recentemente(discord_user_id, c["titulo"], c["artista"])
    ]
    ordenados = sorted(elegiveis, key=lambda c: c.get("popularidade") or 0, reverse=True)

    artistas_usados = set()
    selecao = []
    for candidato in ordenados:
        if len(selecao) >= quantidade:
            break
        artista_normalizado = candidato["artista"].strip().lower()
        if artista_normalizado in artistas_usados:
            continue
        artistas_usados.add(artista_normalizado)
        selecao.append(candidato)

    for candidato in selecao:
        historico_mod.registrar_recomendacao(
            discord_user_id, candidato["titulo"], candidato["artista"],
            reason="em_alta", category="em_alta",
        )
    return selecao

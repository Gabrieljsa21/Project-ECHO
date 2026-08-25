# -*- coding: utf-8 -*-
"""Gera o Radar Musical semanal (seção 7 do ECHO_SPEC) - seleciona e organiza os
candidatos já ranqueados por `core/recomendador.py`, respeitando a composição padrão
(5 compatibilidade / 3 relevância / 2 descoberta / 1 exploração pra 10 músicas) e a
regra de diversidade (máx. 1 faixa por artista por edição). Qualidade tem prioridade
sobre quantidade - nunca preenche a quota com um candidato ruim só pra bater o
número (seção 7.3)."""
import os
import json
from datetime import date

from echo.core import perfil as perfil_mod
from echo.core import recomendador as recomendador_mod
from echo.core import historico as historico_mod

ARQUIVO_ESTADO_RADAR = "data/radar_estado.json"

QUANTIDADE_PADRAO = 10
COMPOSICAO_PADRAO = {
    "compatibilidade": 5,
    "relevancia": 3,
    "descoberta": 2,
    "exploracao": 1,
}
SCORE_MINIMO_QUALIDADE = 0.15


def _carregar_estado():
    if not os.path.exists(ARQUIVO_ESTADO_RADAR):
        return {}
    try:
        with open(ARQUIVO_ESTADO_RADAR, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_estado(estado):
    os.makedirs(os.path.dirname(ARQUIVO_ESTADO_RADAR), exist_ok=True)
    with open(ARQUIVO_ESTADO_RADAR, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def radar_ja_gerado_hoje():
    return _carregar_estado().get("gerado_em") == date.today().isoformat()


def obter_ultimo_radar():
    return _carregar_estado().get("ultimo_radar", [])


def _id_candidato(candidato):
    return f"{candidato['artista'].strip().lower()}::{candidato['titulo'].strip().lower()}"


def _selecionar_com_diversidade(candidatos_categoria, quantidade, artistas_usados):
    selecionados = []
    for candidato in candidatos_categoria:
        if len(selecionados) >= quantidade:
            break
        if candidato["_score"] < SCORE_MINIMO_QUALIDADE:
            break
        artista_normalizado = candidato["artista"].strip().lower()
        if artista_normalizado in artistas_usados:
            continue
        selecionados.append(candidato)
        artistas_usados.add(artista_normalizado)
    return selecionados


def gerar_radar(candidatos, quantidade=QUANTIDADE_PADRAO, composicao=None):
    """`candidatos` já vem do provedor (lançamentos + busca pelos artistas favoritos,
    ver `api_bridge.py`) - esta função só ranqueia e seleciona, nunca busca dado
    externo sozinha (mantém o motor desacoplado do provedor, seção 17)."""
    composicao = composicao or COMPOSICAO_PADRAO
    perfil = perfil_mod.carregar_perfil()
    ranqueados = recomendador_mod.ranquear(candidatos, perfil)

    por_categoria = {categoria: [] for categoria in composicao}
    for candidato in ranqueados:
        if candidato["_categoria"] in por_categoria:
            por_categoria[candidato["_categoria"]].append(candidato)

    artistas_usados = set()
    selecao = []
    for categoria, quota in composicao.items():
        selecao.extend(_selecionar_com_diversidade(por_categoria[categoria], quota, artistas_usados))

    # Se uma categoria não teve candidato de qualidade suficiente pra preencher sua
    # quota, completa em RODÍZIO entre as categorias que ainda têm sobra (1 de cada
    # vez) em vez de um top-up global por score - senão a categoria com peso maior
    # (compatibilidade, 50%) engoliria sozinha toda folga deixada por categorias sem
    # candidato (ex.: descoberta vazia), o que contradiz "respeitar proporções
    # aproximadamente" mesmo quando as outras categorias TÊM candidato de sobra.
    if len(selecao) < quantidade:
        ids_selecionados = {_id_candidato(c) for c in selecao}
        sobra_por_categoria = {
            categoria: [c for c in candidatos_categoria if _id_candidato(c) not in ids_selecionados]
            for categoria, candidatos_categoria in por_categoria.items()
        }
        categorias_ciclo = list(sobra_por_categoria.keys())
        indice = 0
        ciclos_sem_progresso = 0
        while len(selecao) < quantidade and any(sobra_por_categoria.values()) and ciclos_sem_progresso < len(categorias_ciclo):
            categoria = categorias_ciclo[indice % len(categorias_ciclo)]
            indice += 1
            extra = _selecionar_com_diversidade(sobra_por_categoria[categoria], 1, artistas_usados)
            if not extra:
                # nada aproveitável agora (score baixo ou artista já usado) - não
                # adianta tentar de novo com o mesmo estado, evita ciclo infinito
                sobra_por_categoria[categoria] = []
                ciclos_sem_progresso += 1
                continue
            ciclos_sem_progresso = 0
            selecao.extend(extra)
            id_extra = _id_candidato(extra[0])
            sobra_por_categoria[categoria] = [c for c in sobra_por_categoria[categoria] if _id_candidato(c) != id_extra]

    selecao = selecao[:quantidade]

    for candidato in selecao:
        historico_mod.registrar_recomendacao(
            candidato["titulo"], candidato["artista"],
            reason=candidato["_categoria"], category=candidato["_categoria"],
        )

    _salvar_estado({
        "gerado_em": date.today().isoformat(),
        "ultimo_radar": selecao,
    })
    return selecao

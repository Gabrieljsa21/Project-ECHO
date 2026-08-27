# -*- coding: utf-8 -*-
"""Motor de recomendação determinístico (seções 6/19 do ECHO_SPEC) - nunca depende do
LLM pra escolher música, só de metadados/sinais do provedor + perfil. Distribuição
padrão dos pesos (compatibilidade 50% / relevância 25% / descoberta 15% /
exploração 10%) é a mesma usada tanto pro score de cada faixa quanto pra composição
do Radar (`core/radar.py`)."""
from echo.core import historico as historico_mod

PESO_COMPATIBILIDADE = 0.50
PESO_RELEVANCIA = 0.25
PESO_DESCOBERTA = 0.15
PESO_EXPLORACAO = 0.10


def _artista_favorito(candidato, perfil):
    nome = candidato["artista"].strip().lower()
    return any(a["nome"].strip().lower() == nome for a in perfil["favorite_artists"])


def _artista_rejeitado(candidato, perfil):
    nome = candidato["artista"].strip().lower()
    return any(a["nome"].strip().lower() == nome for a in perfil["disliked_artists"])


def _sobreposicao_generos(candidato, perfil):
    """0-1: maior peso de `preferred_genres` entre os gêneros do candidato. 0 se o
    candidato não tem gênero conhecido (provedor não informou) - tratado como sinal
    ausente, nunca inventado."""
    generos_candidato = [g.lower() for g in candidato.get("generos", [])]
    if not generos_candidato:
        return 0.0
    pesos = [perfil["preferred_genres"].get(g, 0.0) for g in generos_candidato]
    return max(pesos) if pesos else 0.0


def _compatibilidade(candidato, perfil):
    score = _sobreposicao_generos(candidato, perfil)
    if _artista_favorito(candidato, perfil):
        score = min(1.0, score + 0.4)
    return score


def _relevancia_atual(candidato):
    popularidade = candidato.get("popularidade")
    return (popularidade / 100) if popularidade is not None else 0.0


def _descoberta(candidato, perfil):
    """Artista novo pra o usuário, mas com alguma compatibilidade de gênero - "parece
    com o que você gosta, mas você ainda não conhece"."""
    if _artista_favorito(candidato, perfil):
        return 0.0
    compat = _sobreposicao_generos(candidato, perfil)
    if compat <= 0:
        return 0.0
    popularidade = candidato.get("popularidade")
    obscuridade = (1.0 - popularidade / 100) if popularidade is not None else 0.5
    return compat * obscuridade


def _exploracao(candidato, perfil):
    """Deliberadamente FORA da bolha (seção 6.4) - baixa sobreposição de gênero com o
    perfil, mas com gênero conhecido o bastante pra ser uma aposta plausível, não uma
    recomendação aleatória."""
    if not candidato.get("generos"):
        return 0.0
    compat = _sobreposicao_generos(candidato, perfil)
    return max(0.0, 1.0 - compat) if compat < 0.3 else 0.0


def _penalidade_diversidade_sessao(candidato, penalidades_sessao):
    """`penalidades_sessao` (2026-08-26, pedido do usuário: "Evitar repetição
    excessiva de artista, gênero ou estilo durante uma mesma sessão") -
    `{"artista::nome": contagem, "genero::nome": contagem}` de quantas vezes
    já tocou NESTA sessão. Reduz o score proporcionalmente - diversidade, não
    dedup exato (o mesmo item pode voltar a ficar atraente depois de um
    tempo, só fica temporariamente pra trás)."""
    if not penalidades_sessao:
        return 0.0
    penalidade = penalidades_sessao.get(f"artista::{candidato['artista'].strip().lower()}", 0) * 0.15
    for genero in candidato.get("generos", []):
        penalidade += penalidades_sessao.get(f"genero::{genero.lower()}", 0) * 0.05
    return penalidade


def calcular_score(discord_user_id, candidato, perfil, penalidades_sessao=None):
    """Devolve (score_total, categoria_dominante). Categoria é None quando o
    candidato é excluído de vez (repetição recente ou artista já rejeitado/feedback
    negativo) - não é "menos preferido", é redundante ou indesejado."""
    if historico_mod.foi_recomendada_recentemente(discord_user_id, candidato["titulo"], candidato["artista"]):
        return -1.0, None
    if _artista_rejeitado(candidato, perfil) or historico_mod.artista_tem_feedback_negativo(discord_user_id, candidato["artista"]):
        return -1.0, None

    componentes = {
        "compatibilidade": _compatibilidade(candidato, perfil) * PESO_COMPATIBILIDADE,
        "relevancia": _relevancia_atual(candidato) * PESO_RELEVANCIA,
        "descoberta": _descoberta(candidato, perfil) * PESO_DESCOBERTA,
        "exploracao": _exploracao(candidato, perfil) * PESO_EXPLORACAO,
    }
    categoria_dominante = max(componentes, key=componentes.get)
    score = sum(componentes.values()) - _penalidade_diversidade_sessao(candidato, penalidades_sessao)
    return score, categoria_dominante


def ranquear(discord_user_id, candidatos, perfil, penalidades_sessao=None):
    """Só os candidatos com score > 0, ordenados do maior pro menor, cada um com
    `_score`/`_categoria` anexados pro `core/radar.py`/`core/pool.py` montar a
    seleção."""
    ranqueados = []
    for candidato in candidatos:
        score, categoria = calcular_score(discord_user_id, candidato, perfil, penalidades_sessao)
        if score > 0:
            ranqueados.append({**candidato, "_score": score, "_categoria": categoria})
    ranqueados.sort(key=lambda c: c["_score"], reverse=True)
    return ranqueados

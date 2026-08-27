# -*- coding: utf-8 -*-
"""Pool pessoal de candidatos musicais (2026-08-26, pedido do usuário: "prefiro
pré-calcular o repertório do que reconstruir recomendações toda vez que o
comando é executado"). Diferente do Radar semanal (lote FECHADO de 10 músicas
curadas com diversidade pra 1 edição), o pool é um reservatório MAIOR (100-300
por pessoa) que o `/caos`/continuação do ERIS consomem ao vivo - sem chamada de
rede no caminho crítico entre uma faixa acabar e a próxima começar.

Reaproveita a MESMA rodada de descoberta semanal do Radar (`core/radar.py`
chama `gerar_pool_incremental` logo depois de ranquear) - o pool nunca dispara
sozinho uma busca no provedor; quem varre o Last.fm continua sendo só o Radar
(1x/semana) ou a descoberta de emergência em `continuacao.py` (fallback raro).

INCREMENTAL, não recriado do zero (seção pedida pelo usuário: "o pool deve ser
incremental... novas rodadas adicionam candidatos, atualizam scores e removem
entradas inválidas ou obsoletas") - preserva o que ainda não foi consumido
entre uma rodada de descoberta e outra."""
import os
import json
import random
from datetime import date

from echo.core import historico as historico_mod

ARQUIVO_POOL = "data/pool_musical.json"
TAMANHO_ALVO = 200

# 🔥 Sorteio entre as TOP N por score, não sempre a 1ª (2026-08-27, achado
# real: com "Musicas sem voto não saem do pool" - `consumir_proxima` parou
# de remover a faixa escolhida do pool - `max()` estrito virou determinístico
# demais: sessões novas (exclusão de sessão vazia) sempre batiam na MESMA
# faixa de maior afinidade toda vez, ex.: "/caos" 3x seguidas sempre
# devolvendo "Duvet - bôa"). `random.choice` entre as top N preserva "prefere
# afinidade alta" sem virar sempre a mesma escolha.
TAMANHO_TOPO_SORTEIO = 5

# 🔥 Boost de proximidade da semente (2026-08-26) - em memória, sem rede: quando
# o ERIS pede "próxima parecida com X", isso favorece o mesmo artista/gênero da
# faixa tocando agora dentro do pool já calculado, sem precisar buscar nada novo.
BOOST_MESMO_ARTISTA = 0.3
BOOST_GENERO_EM_COMUM = 0.15


def _id_candidato(candidato):
    return f"{candidato['artista'].strip().lower()}::{candidato['titulo'].strip().lower()}"


def _carregar_todos():
    if not os.path.exists(ARQUIVO_POOL):
        return {}
    try:
        with open(ARQUIVO_POOL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_todos(todos):
    os.makedirs(os.path.dirname(ARQUIVO_POOL), exist_ok=True)
    with open(ARQUIVO_POOL, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def carregar_pool(discord_user_id):
    return _carregar_todos().get(str(discord_user_id), {}).get("candidatos", [])


def _salvar_pool(discord_user_id, candidatos):
    todos = _carregar_todos()
    todos[str(discord_user_id)] = {
        "candidatos": candidatos,
        "atualizado_em": date.today().isoformat(),
    }
    _salvar_todos(todos)


def pool_vazio_ou_velho(discord_user_id, dias_max=7):
    entrada = _carregar_todos().get(str(discord_user_id))
    if not entrada or not entrada.get("candidatos"):
        return True
    atualizado_em = entrada.get("atualizado_em")
    if not atualizado_em:
        return True
    return (date.today() - date.fromisoformat(atualizado_em)).days > dias_max


def gerar_pool_incremental(discord_user_id, candidatos_ranqueados, tamanho_alvo=TAMANHO_ALVO):
    """Funde o pool existente com os candidatos recém-ranqueados: atualiza score
    de quem já estava lá, adiciona os novos, remove quem já recebeu VOTO
    (`historico.foi_votada` - só sai quem foi avaliado de verdade, pedido do
    usuário 2026-08-26: "Musicas sem voto não saem do pool" - tocar sem
    avaliar não tira a música do repertório). NUNCA recria do zero."""
    pool_atual = {_id_candidato(c): c for c in carregar_pool(discord_user_id)}

    for candidato in candidatos_ranqueados:
        chave = _id_candidato(candidato)
        if historico_mod.foi_votada(discord_user_id, candidato["titulo"], candidato["artista"]):
            pool_atual.pop(chave, None)
            continue
        entrada_pool = {
            "titulo": candidato["titulo"],
            "artista": candidato["artista"],
            "generos": candidato.get("generos", []),
            "afinidade": candidato["_score"],
            "origem": candidato.get("fonte") or candidato["_categoria"],
            "artista_semente": candidato.get("artista"),
            "descoberto_em": pool_atual.get(chave, {}).get("descoberto_em", date.today().isoformat()),
        }
        pool_atual[chave] = entrada_pool

    # 🔥 Remove quem ficou pra trás demais (score baixo) se o pool passar do
    # alvo - mantém só os mais afins, não deixa crescer sem limite.
    candidatos_finais = sorted(pool_atual.values(), key=lambda c: c["afinidade"], reverse=True)[:tamanho_alvo]
    _salvar_pool(discord_user_id, candidatos_finais)
    return candidatos_finais


def _boost_proximidade(candidato, seed_artista, seed_generos):
    boost = 0.0
    if seed_artista and candidato["artista"].strip().lower() == seed_artista.strip().lower():
        boost += BOOST_MESMO_ARTISTA
    if seed_generos:
        generos_candidato = {g.lower() for g in candidato.get("generos", [])}
        if generos_candidato & {g.lower() for g in seed_generos}:
            boost += BOOST_GENERO_EM_COMUM
    return boost


def _penalidade_diversidade(candidato, penalidades_sessao):
    if not penalidades_sessao:
        return 0.0
    penalidade = penalidades_sessao.get(f"artista::{candidato['artista'].strip().lower()}", 0) * 0.15
    for genero in candidato.get("generos", []):
        penalidade += penalidades_sessao.get(f"genero::{genero.lower()}", 0) * 0.05
    return penalidade


def consumir_proxima(discord_user_id, seed_artista=None, seed_generos=None, excluidos_sessao=None, penalidades_sessao=None):
    """Devolve uma entrada sorteada entre as `TAMANHO_TOPO_SORTEIO` de maior
    score do pool - `None` se o pool estiver vazio (quem chama decide o
    fallback, ver `continuacao.py`). Registra em `historico` (reason="pool",
    sem voto ainda) - alimenta o dedup de 90 dias do Radar semanal e fica
    pronta pra receber um voto depois.

    🔥 NÃO remove do pool (2026-08-26, pedido do usuário: "Musicas sem
    voto não saem do pool") - dedup de CURTO prazo (não repetir na mesma
    sessão) é responsabilidade de `excluidos_sessao`, de quem chama; só sai
    do pool de vez quando recebe um voto de verdade (`feedback.py` chama
    `remover_track`), ou quando uma rodada de descoberta a filtra via
    `historico.foi_votada` em `gerar_pool_incremental`."""
    pool = carregar_pool(discord_user_id)
    if not pool:
        return None

    excluidos_normalizados = {e.lower() for e in (excluidos_sessao or [])}
    candidatos_validos = [c for c in pool if _id_candidato(c) not in excluidos_normalizados]
    if not candidatos_validos:
        return None

    candidatos_ordenados = sorted(
        candidatos_validos,
        key=lambda c: c["afinidade"] + _boost_proximidade(c, seed_artista, seed_generos) - _penalidade_diversidade(c, penalidades_sessao),
        reverse=True,
    )
    escolhida = random.choice(candidatos_ordenados[:TAMANHO_TOPO_SORTEIO])
    historico_mod.registrar_recomendacao(discord_user_id, escolhida["titulo"], escolhida["artista"], reason="pool", category=escolhida.get("origem"))
    return escolhida


def remover_track(discord_user_id, titulo, artista):
    """Sai do pool assim que recebe voto (positivo OU negativo) - chamado
    por `feedback.py` em toda avaliação explícita (2026-08-26). Só a FAIXA
    EXATA - um voto numa música nunca mexe em mais nada do mesmo artista
    (2026-08-27, pedido do usuário: "um 👎 em 1 musica n pode condenar
    todas desse artista. Assim como o like n aprova todas tbm, algumas eu
    gosto e outras nao" - `invalidar_relacionados`, que removia o artista
    inteiro num 👎, foi removido por esse mesmo motivo)."""
    pool = carregar_pool(discord_user_id)
    alvo = _id_candidato({"artista": artista, "titulo": titulo})
    pool_filtrado = [c for c in pool if _id_candidato(c) != alvo]
    if len(pool_filtrado) != len(pool):
        _salvar_pool(discord_user_id, pool_filtrado)
    return pool_filtrado

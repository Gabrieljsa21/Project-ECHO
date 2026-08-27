# -*- coding: utf-8 -*-
"""Continuação ao vivo do Radar Musical (2026-08-25, pedido do usuário: "quero
q alguem seja meu dj exclusivo, q conheça meus gostos e q qnd eu pedir uma
musica, ele continue tocando outras em sequencia na mesma vibe").

🔥 Reescrito pra consumir o POOL pré-calculado (2026-08-26, pedido do usuário:
"prefiro pré-calcular o repertório do que reconstruir recomendações toda vez
que o comando é executado") - o caminho NORMAL não faz mais chamada de rede
nenhuma, só lê `core/pool.py`. Cadeia de fallback em camadas (pedido do
usuário): **pool pessoal → aprovadas dessa pessoa → descoberta emergencial
síncrona (rede, só quando os dois primeiros falharem) → None**."""
import random

from echo.core import recomendador as recomendador_mod
from echo.core import historico as historico_mod
from echo.core import pool as pool_mod
from echo.providers import ProvedorIndisponivel

LIMITE_DESCOBERTA_EMERGENCIAL = 15


def _id_faixa(artista, titulo):
    return f"{artista.strip().lower()}::{titulo.strip().lower()}"


def _de_aprovada(entrada):
    return {
        "titulo": entrada["titulo"],
        "artista": entrada["artista"],
        "generos": [],
        "_score": 0.5,
        "_categoria": "aprovada",
    }


def _aprovada_aleatoria_nao_excluida(discord_user_id, excluidos_normalizados):
    """SORTEADA entre as elegíveis (2026-08-27, achado real: com o pool
    ainda vazio - antes da 1ª geração do Radar - `/caos` caía direto nessa
    camada, e como cada chamada é uma sessão NOVA, a exclusão de sessão
    reseta, sempre sobrando a mesma faixa em primeiro. Pegar sempre a
    PRIMEIRA da lista fazia `/caos` repetir a mesma música toda vez que
    a sessão recomeçava - confirmado em produção: "Counting Stars" 3x
    seguidas). Random é aceitável aqui - só decide qual candidato entre os
    já aprovados abrir a sessão, não afeta o ranking determinístico."""
    candidatas = [e for e in historico_mod.obter_aprovadas(discord_user_id) if e["track_id"] not in excluidos_normalizados]
    if not candidatas:
        return None
    return _de_aprovada(random.choice(candidatas))


def sugerir_proxima(discord_user_id, provedor, artista_atual, titulo_atual, excluidos=None, penalidades_sessao=None):
    """`excluidos`: lista de "artista::titulo" já tocados NESTA sessão de call
    (dedup de CURTO prazo). Devolve o candidato de maior afinidade, ou None se
    não achar nada de qualidade em NENHUMA camada do fallback (nunca inventa
    uma música)."""
    excluidos_normalizados = {e.lower() for e in (excluidos or [])}
    excluidos_normalizados.add(_id_faixa(artista_atual, titulo_atual))

    generos_semente = []
    try:
        generos_semente = provedor.resolver_generos([artista_atual]).get(artista_atual.strip().lower(), [])
    except ProvedorIndisponivel:
        pass

    # Camada 1: pool pessoal já pré-calculado - sem rede.
    proxima = pool_mod.consumir_proxima(
        discord_user_id, seed_artista=artista_atual, seed_generos=generos_semente,
        excluidos_sessao=excluidos_normalizados, penalidades_sessao=penalidades_sessao,
    )
    if proxima:
        return proxima

    # Camada 2: aprovadas dessa pessoa (feedback explícito 👍 já dado antes).
    proxima = _aprovada_aleatoria_nao_excluida(discord_user_id, excluidos_normalizados)
    if proxima:
        return proxima

    # Camada 3: descoberta emergencial síncrona (rede) - mesmo caminho de
    # antes desta reescrita, só como último recurso.
    candidatos = []
    try:
        candidatos.extend(provedor.obter_faixas_do_artista(artista_atual, limite=15))
    except ProvedorIndisponivel:
        pass
    for genero in generos_semente[:3]:
        try:
            candidatos.extend(provedor.obter_faixas_por_tag(genero, limite=15))
        except ProvedorIndisponivel:
            pass
    candidatos_filtrados = [c for c in candidatos if _id_faixa(c["artista"], c["titulo"]) not in excluidos_normalizados]
    if not candidatos_filtrados:
        return None

    from echo.core import perfil as perfil_mod
    perfil = perfil_mod.carregar_perfil(discord_user_id)
    # 🔥 Perfil EFETIVO (cópia, nunca persistida) - trata o artista/gêneros da
    # faixa atual como preferência forte pra ESSA sugestão (mesmo raciocínio
    # de antes: "a mesma vibe" precisa reagir ao pedido imediato).
    perfil_efetivo = {
        **perfil,
        "favorite_artists": list(perfil["favorite_artists"]),
        "preferred_genres": dict(perfil["preferred_genres"]),
    }
    if not any(a["nome"].strip().lower() == artista_atual.strip().lower() for a in perfil_efetivo["favorite_artists"]):
        perfil_efetivo["favorite_artists"].append({
            "nome": artista_atual, "genero": generos_semente[0] if generos_semente else None,
        })
    for genero in generos_semente:
        perfil_efetivo["preferred_genres"][genero] = max(perfil_efetivo["preferred_genres"].get(genero, 0.0), 0.8)

    ranqueados = recomendador_mod.ranquear(discord_user_id, candidatos_filtrados, perfil_efetivo, penalidades_sessao)
    return ranqueados[0] if ranqueados else None


def sugerir_semente(discord_user_id, provedor=None, excluidos=None, penalidades_sessao=None):
    """Primeira sugestão de uma sessão contínua SEM faixa/artista de partida
    (2026-08-26, pedido do usuário via `/caos` no ERIS: "sem exigir artista,
    gênero, música ou qualquer outra referência inicial"). `provedor` só é
    usado na camada 3 (emergência) - se o pool e as aprovadas já resolverem,
    nem precisa. Devolve None se não achar nada de qualidade em NENHUMA
    camada."""
    excluidos_normalizados = {e.lower() for e in (excluidos or [])}

    # Camada 1: pool pessoal já pré-calculado - sem rede.
    semente = pool_mod.consumir_proxima(discord_user_id, excluidos_sessao=excluidos_normalizados, penalidades_sessao=penalidades_sessao)
    if semente:
        return semente

    # Camada 2: aprovadas dessa pessoa.
    semente = _aprovada_aleatoria_nao_excluida(discord_user_id, excluidos_normalizados)
    if semente:
        return semente

    # Camada 3: descoberta emergencial síncrona (rede) - só se o pool nunca
    # foi gerado ainda (usuário novo) ou secou de vez.
    if provedor is None:
        return None
    try:
        candidatos = list(provedor.obter_lancamentos_novos(LIMITE_DESCOBERTA_EMERGENCIAL))
    except ProvedorIndisponivel:
        return None
    candidatos_filtrados = [c for c in candidatos if _id_faixa(c["artista"], c["titulo"]) not in excluidos_normalizados]
    if not candidatos_filtrados:
        return None

    from echo.core import perfil as perfil_mod
    perfil = perfil_mod.carregar_perfil(discord_user_id)
    ranqueados = recomendador_mod.ranquear(discord_user_id, candidatos_filtrados, perfil, penalidades_sessao)
    return ranqueados[0] if ranqueados else None

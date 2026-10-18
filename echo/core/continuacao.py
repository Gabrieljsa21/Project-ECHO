# -*- coding: utf-8 -*-
"""Continuação ao vivo do Radar Musical (2026-08-25, pedido do usuário: "quero
q alguem seja meu dj exclusivo, q conheça meus gostos e q qnd eu pedir uma
musica, ele continue tocando outras em sequencia na mesma vibe").

🔥 Reescrito pra consumir o POOL pré-calculado (2026-08-26, pedido do usuário:
"prefiro pré-calcular o repertório do que reconstruir recomendações toda vez
que o comando é executado") - o caminho NORMAL não faz mais chamada de rede
nenhuma, só lê `core/pool.py`. Cadeia de fallback em camadas (pedido do
usuário): **pool pessoal → descoberta emergencial síncrona (rede, só quando
o pool não resolver) → None**.

🔥 Sem cair nas aprovadas (2026-10-06, pedido do usuário: o Caos tocava
músicas curtidas) - a antiga Camada 2 sorteava entre as faixas com 👍
sempre que o pool não tinha nada livre pra sessão. O Caos é descoberta:
faixa já votada (👍 ou 👎, inclusive variante ao vivo/remix) nunca sai
daqui, em nenhuma camada.

Antes das camadas, a regra das 5 chances (`artistas.py`, 2026-09-26): a
cada `artistas.INTERVALO_PROVA` sugestões, entra uma faixa de algum artista
"em prova", se houver."""

from echo.core import artistas as artistas_mod
from echo.core import recomendador as recomendador_mod
from echo.core import historico as historico_mod
from echo.core import pool as pool_mod
from echo.core import versoes as versoes_mod
from echo.providers import ProvedorIndisponivel

LIMITE_DESCOBERTA_EMERGENCIAL = 15


def _id_faixa(artista, titulo):
    return f"{artista.strip().lower()}::{titulo.strip().lower()}"


def _filtrar_novas(discord_user_id, candidatos, excluidos_normalizados):
    """Tira da descoberta emergencial o que já tocou nesta sessão e o que já
    foi votado (mesma regra do pool)."""
    votadas = historico_mod.chaves_frouxas_votadas(discord_user_id)
    return [
        c for c in candidatos
        if _id_faixa(c["artista"], c["titulo"]) not in excluidos_normalizados
        and historico_mod.chave_frouxa(c["titulo"], c["artista"]) not in votadas
    ]


def _registrar(faixa, camada):
    """Log de cada sugestão (2026-10-06, pedido do usuário: "um log das
    músicas passando e tudo que tá acontecendo")."""
    if faixa:
        print(f" [ECHO] Caos ({camada}) -> {faixa['artista']} - {faixa['titulo']}")
    else:
        print(f" [ECHO] Caos ({camada}) -> nenhuma faixa nova encontrada")
    return faixa


def sugerir_proxima(discord_user_id, provedor, artista_atual, titulo_atual, excluidos=None, penalidades_sessao=None):
    """`excluidos`: lista de "artista::titulo" já tocados NESTA sessão de call
    (dedup de CURTO prazo). Devolve o candidato de maior afinidade, ou None se
    não achar nada de qualidade em NENHUMA camada do fallback (nunca inventa
    uma música)."""
    excluidos_normalizados = {e.lower() for e in (excluidos or [])}
    excluidos_normalizados.add(_id_faixa(artista_atual, titulo_atual))

    prova = artistas_mod.proxima_faixa_de_prova(discord_user_id, excluidos_normalizados)
    if prova:
        return _registrar(prova, "artista em prova")

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

    # Camada 2: descoberta emergencial síncrona (rede), só como último recurso.
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
    candidatos = versoes_mod.oficializar(provedor, candidatos)
    candidatos_filtrados = _filtrar_novas(discord_user_id, candidatos, excluidos_normalizados)
    if not candidatos_filtrados:
        return _registrar(None, "descoberta emergencial")

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
    return _registrar(ranqueados[0] if ranqueados else None, "descoberta emergencial")


def sugerir_semente(discord_user_id, provedor=None, excluidos=None, penalidades_sessao=None):
    """Primeira sugestão de uma sessão contínua SEM faixa/artista de partida
    (2026-08-26, pedido do usuário via `/caos` no ERIS: "sem exigir artista,
    gênero, música ou qualquer outra referência inicial"). `provedor` só é
    usado na camada 2 (emergência) - se o pool já resolver, nem precisa. Devolve None se não achar nada de qualidade em NENHUMA
    camada."""
    excluidos_normalizados = {e.lower() for e in (excluidos or [])}

    prova = artistas_mod.proxima_faixa_de_prova(discord_user_id, excluidos_normalizados)
    if prova:
        return _registrar(prova, "artista em prova")

    # Camada 1: pool pessoal já pré-calculado - sem rede.
    semente = pool_mod.consumir_proxima(discord_user_id, excluidos_sessao=excluidos_normalizados, penalidades_sessao=penalidades_sessao)
    if semente:
        return semente

    # Camada 2: descoberta emergencial síncrona (rede) - só se o pool nunca
    # foi gerado ainda (usuário novo) ou secou de vez.
    if provedor is None:
        return _registrar(None, "sem provedor")
    try:
        candidatos = list(provedor.obter_lancamentos_novos(LIMITE_DESCOBERTA_EMERGENCIAL))
    except ProvedorIndisponivel:
        return _registrar(None, "provedor indisponível")
    candidatos = versoes_mod.oficializar(provedor, candidatos)
    candidatos_filtrados = _filtrar_novas(discord_user_id, candidatos, excluidos_normalizados)
    if not candidatos_filtrados:
        return _registrar(None, "descoberta emergencial")

    from echo.core import perfil as perfil_mod
    perfil = perfil_mod.carregar_perfil(discord_user_id)
    ranqueados = recomendador_mod.ranquear(discord_user_id, candidatos_filtrados, perfil, penalidades_sessao)
    return _registrar(ranqueados[0] if ranqueados else None, "descoberta emergencial")

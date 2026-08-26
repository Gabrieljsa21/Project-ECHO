# -*- coding: utf-8 -*-
"""Continuação ao vivo do Radar Musical (2026-08-25, pedido do usuário: "quero
q alguem seja meu dj exclusivo, q conheça meus gostos e q qnd eu pedir uma
musica, ele continue tocando outras em sequencia na mesma vibe"). Diferente do
`radar.py` (lote fechado de 10 músicas pra uma semana), aqui é UMA sugestão
por vez, semeada pela faixa que está tocando AGORA numa call de verdade
(Project ERIS toca; aqui só decide QUAL é a próxima)."""
from echo.core import recomendador as recomendador_mod
from echo.providers import ProvedorIndisponivel


def _id_faixa(artista, titulo):
    return f"{artista.strip().lower()}::{titulo.strip().lower()}"


def sugerir_proxima(provedor, perfil, artista_atual, titulo_atual, excluidos=None):
    """`excluidos`: lista de "artista::titulo" já tocados NESTA sessão de call
    (dedup de CURTO prazo - resolve a queixa real do usuário sobre o Jockie
    repetir depois de um tempo, diferente do `DIAS_REDESCOBERTA` de 90 dias do
    Radar semanal, que `core.recomendador.ranquear` também aplica por baixo
    como segunda camada). Devolve o candidato de maior score, ou None se não
    achar nada de qualidade (nunca inventa uma música)."""
    excluidos_normalizados = {e.lower() for e in (excluidos or [])}
    excluidos_normalizados.add(_id_faixa(artista_atual, titulo_atual))

    generos_semente = []
    try:
        generos_semente = provedor.resolver_generos([artista_atual]).get(artista_atual.strip().lower(), [])
    except ProvedorIndisponivel:
        pass

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

    # 🔥 Perfil EFETIVO (cópia, nunca persistida) - trata o artista/gêneros da
    # faixa atual como preferência forte pra ESSA sugestão, mesmo que ainda
    # não estejam no perfil de longo prazo (o usuário pode ter pedido uma
    # música avulsa sem nunca ter cadastrado o artista como favorito - "a
    # mesma vibe" precisa reagir ao pedido imediato, não só ao histórico
    # salvo em disco).
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

    ranqueados = recomendador_mod.ranquear(candidatos_filtrados, perfil_efetivo)
    return ranqueados[0] if ranqueados else None


def sugerir_semente(candidatos, perfil, excluidos=None):
    """Primeira sugestão de uma sessão contínua SEM faixa/artista de partida
    (2026-08-26, pedido do usuário via `/caos` no ERIS: "sem exigir artista,
    gênero, música ou qualquer outra referência inicial"). Diferente de
    `sugerir_proxima`, não há faixa atual pra semear busca/gênero - por isso
    `candidatos` já vem coletado pelo chamador com a mesma composição de 3
    fontes do Radar semanal (chart global + artistas favoritos + gêneros
    preferidos, ver `api_bridge.py::_coletar_candidatos`), o que garante
    resultado mesmo com perfil totalmente vazio (chart global sozinho já
    supre candidato). `excluidos`: "artista::titulo" a ignorar (dedup de
    sessão, mesmo campo de `sugerir_proxima`). Devolve o candidato de maior
    score pelo perfil real (sem boost artificial - não há pedido explícito
    pra reforçar), ou None se não achar nada de qualidade."""
    excluidos_normalizados = {e.lower() for e in (excluidos or [])}
    candidatos_filtrados = [c for c in candidatos if _id_faixa(c["artista"], c["titulo"]) not in excluidos_normalizados]
    if not candidatos_filtrados:
        return None
    ranqueados = recomendador_mod.ranquear(candidatos_filtrados, perfil)
    return ranqueados[0] if ranqueados else None

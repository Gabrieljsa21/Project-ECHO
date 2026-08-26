# -*- coding: utf-8 -*-
"""Perfil musical persistente do Modo DJ (seção 4 do ECHO_SPEC) - artistas/gêneros
favoritos e rejeitados, nível de descoberta. Cadastro manual (Fase 1) OU importado
do histórico real de escuta via Last.fm/scrobbling (Fase 2 antecipada, ver
`importar_favoritos_do_historico` - precisa de `LASTFM_USERNAME` vinculado)."""
import os
import json

ARQUIVO_PERFIL = "data/perfil.json"

_PERFIL_PADRAO = {
    "favorite_artists": [],
    "disliked_artists": [],
    "liked_tracks": [],
    "disliked_tracks": [],
    "preferred_genres": {},
    "preferred_eras": {},
    "discovery_level": 0.5,
}


def carregar_perfil():
    if not os.path.exists(ARQUIVO_PERFIL):
        return json.loads(json.dumps(_PERFIL_PADRAO))
    try:
        with open(ARQUIVO_PERFIL, "r", encoding="utf-8") as f:
            perfil = json.load(f)
    except Exception:
        return json.loads(json.dumps(_PERFIL_PADRAO))
    for chave, valor in _PERFIL_PADRAO.items():
        perfil.setdefault(chave, valor)
    return perfil


def salvar_perfil(perfil):
    os.makedirs(os.path.dirname(ARQUIVO_PERFIL), exist_ok=True)
    with open(ARQUIVO_PERFIL, "w", encoding="utf-8") as f:
        json.dump(perfil, f, ensure_ascii=False, indent=2)


def adicionar_artista_favorito(nome, genero=None):
    perfil = carregar_perfil()
    nome_normalizado = nome.strip().lower()
    perfil["disliked_artists"] = [a for a in perfil["disliked_artists"] if a["nome"].strip().lower() != nome_normalizado]
    if not any(a["nome"].strip().lower() == nome_normalizado for a in perfil["favorite_artists"]):
        perfil["favorite_artists"].append({"nome": nome, "genero": genero})
    if genero:
        ajustar_peso_genero(perfil, genero, 0.2)
    salvar_perfil(perfil)
    return perfil


def adicionar_artista_rejeitado(nome):
    perfil = carregar_perfil()
    nome_normalizado = nome.strip().lower()
    perfil["favorite_artists"] = [a for a in perfil["favorite_artists"] if a["nome"].strip().lower() != nome_normalizado]
    if not any(a["nome"].strip().lower() == nome_normalizado for a in perfil["disliked_artists"]):
        perfil["disliked_artists"].append({"nome": nome})
    salvar_perfil(perfil)
    return perfil


def definir_peso_genero(nome_genero, peso):
    perfil = carregar_perfil()
    perfil["preferred_genres"][nome_genero] = max(0.0, min(1.0, peso))
    salvar_perfil(perfil)
    return perfil


def ajustar_peso_genero(perfil, nome_genero, delta):
    """Ajusta incrementalmente (nunca substitui) - usado pelo feedback do Radar e
    pelo cadastro manual de artista favorito; nunca deixa o peso sair de [0, 1]
    (seção 21: uma única ação não deve alterar radicalmente o perfil)."""
    atual = perfil["preferred_genres"].get(nome_genero, 0.5)
    perfil["preferred_genres"][nome_genero] = max(0.0, min(1.0, atual + delta))


def definir_discovery_level(valor):
    perfil = carregar_perfil()
    perfil["discovery_level"] = max(0.0, min(1.0, valor))
    salvar_perfil(perfil)
    return perfil


def importar_favoritos_do_historico(artistas_ranqueados):
    """Seed do perfil a partir do histórico REAL de escuta (`provedor.
    obter_top_artistas_usuario`, requer `LASTFM_USERNAME`) - `artistas_ranqueados`:
    lista de `{"nome", "rank", "generos"}`, mais tocado primeiro. Peso de gênero
    proporcional à posição no ranking (mais tocado = mais peso) - nunca DIMINUI um
    peso que já esteja mais alto que o calculado aqui, pra uma importação em lote
    nunca apagar um ajuste fino que o usuário já fez via feedback manual (seção 21:
    "manter possibilidade de o usuário redefinir ou editar preferências
    manualmente" continua valendo pro lado positivo). Respeita `disliked_artists`
    - nunca reimporta quem o usuário já rejeitou explicitamente."""
    perfil = carregar_perfil()
    total = len(artistas_ranqueados) or 1
    rejeitados = {a["nome"].strip().lower() for a in perfil["disliked_artists"]}
    favoritos_atuais = {a["nome"].strip().lower() for a in perfil["favorite_artists"]}

    for artista in artistas_ranqueados:
        nome_normalizado = artista["nome"].strip().lower()
        if nome_normalizado in rejeitados:
            continue
        if nome_normalizado not in favoritos_atuais:
            generos_artista = artista.get("generos") or []
            perfil["favorite_artists"].append({"nome": artista["nome"], "genero": generos_artista[0] if generos_artista else None})
            favoritos_atuais.add(nome_normalizado)

        peso_pela_posicao = round(max(0.1, 1.0 - (artista.get("rank", total) - 1) / total), 2)
        for genero in artista.get("generos", []):
            atual = perfil["preferred_genres"].get(genero, 0.0)
            perfil["preferred_genres"][genero] = max(atual, peso_pela_posicao)

    salvar_perfil(perfil)
    return perfil

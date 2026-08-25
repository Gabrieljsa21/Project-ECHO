# -*- coding: utf-8 -*-
"""Perfil musical persistente do Modo DJ (seção 4 do ECHO_SPEC) - artistas/gêneros
favoritos e rejeitados, nível de descoberta. Cadastro é manual nesta fase (Fase 1) -
sem histórico de reprodução real ainda (Fase 2, comportamento real do provedor)."""
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

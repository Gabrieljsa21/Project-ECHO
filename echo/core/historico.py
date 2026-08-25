# -*- coding: utf-8 -*-
"""Histórico de recomendações do Radar Musical (seção 8 do ECHO_SPEC) - evita
repetição desnecessária e guarda o feedback de cada faixa recomendada. Permite
redescoberta só depois de `DIAS_REDESCOBERTA` (seção 9), nunca reaparece só porque
continua popular."""
import os
import json
from datetime import date, timedelta

ARQUIVO_HISTORICO = "data/historico_recomendacoes.json"
DIAS_REDESCOBERTA = 90


def _track_id(titulo, artista):
    return f"{artista.strip().lower()}::{titulo.strip().lower()}"


def carregar_historico():
    if not os.path.exists(ARQUIVO_HISTORICO):
        return []
    try:
        with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _salvar_historico(historico):
    os.makedirs(os.path.dirname(ARQUIVO_HISTORICO), exist_ok=True)
    with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def foi_recomendada_recentemente(titulo, artista, dias=DIAS_REDESCOBERTA):
    track_id = _track_id(titulo, artista)
    limite = date.today() - timedelta(days=dias)
    for entrada in carregar_historico():
        if entrada["track_id"] == track_id and date.fromisoformat(entrada["recommended_at"]) >= limite:
            return True
    return False


def registrar_recomendacao(titulo, artista, reason, category):
    historico = carregar_historico()
    historico.append({
        "track_id": _track_id(titulo, artista),
        "titulo": titulo,
        "artista": artista,
        "recommended_at": date.today().isoformat(),
        "reason": reason,
        "category": category,
        "user_feedback": None,
        "subsequent_play_count": 0,
    })
    _salvar_historico(historico)


def registrar_feedback(track_id, feedback):
    """feedback: "positivo" ou "negativo". Marca a entrada MAIS RECENTE desse
    track_id - se a mesma música foi recomendada mais de uma vez, o feedback é sobre a
    última edição do Radar em que ela apareceu."""
    historico = carregar_historico()
    for entrada in reversed(historico):
        if entrada["track_id"] == track_id:
            entrada["user_feedback"] = feedback
            _salvar_historico(historico)
            return entrada
    return None


def obter_historico(limite=20):
    return list(reversed(carregar_historico()))[:limite]


def artista_tem_feedback_negativo(artista):
    artista_normalizado = artista.strip().lower()
    return any(
        e["artista"].strip().lower() == artista_normalizado and e["user_feedback"] == "negativo"
        for e in carregar_historico()
    )

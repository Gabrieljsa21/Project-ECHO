# -*- coding: utf-8 -*-
"""Histórico de recomendações do Radar Musical (seção 8 do ECHO_SPEC) - evita
repetição desnecessária e guarda o feedback de cada faixa recomendada. Permite
redescoberta só depois de `DIAS_REDESCOBERTA` (seção 9), nunca reaparece só porque
continua popular.

🔥 Por pessoa (2026-08-26) - toda entrada agora carrega `discord_user_id`, e toda
função de consulta/escrita exige isso como parâmetro (mesmo motivo de
`perfil.py`: Modo Música é social, feedback de um visitante não pode contar
como se fosse do dono)."""
import os
import json
from datetime import date, timedelta

ARQUIVO_HISTORICO = "data/historico_recomendacoes.json"
ARQUIVO_EVENTOS_ESCUTA = "data/eventos_escuta.json"
DIAS_REDESCOBERTA = 90


def track_id(titulo, artista):
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


def _do_usuario(historico, discord_user_id):
    discord_user_id = str(discord_user_id)
    return [e for e in historico if e.get("discord_user_id") == discord_user_id]


def foi_recomendada_recentemente(discord_user_id, titulo, artista, dias=DIAS_REDESCOBERTA):
    """Dedup de 90 dias (Radar semanal) - por pessoa."""
    id_alvo = track_id(titulo, artista)
    limite = date.today() - timedelta(days=dias)
    for entrada in _do_usuario(carregar_historico(), discord_user_id):
        if entrada["track_id"] == id_alvo and date.fromisoformat(entrada["recommended_at"]) >= limite:
            return True
    return False


def registrar_recomendacao(discord_user_id, titulo, artista, reason, category):
    historico = carregar_historico()
    historico.append({
        "discord_user_id": str(discord_user_id),
        "track_id": track_id(titulo, artista),
        "titulo": titulo,
        "artista": artista,
        "recommended_at": date.today().isoformat(),
        "reason": reason,
        "category": category,
        "user_feedback": None,
        "subsequent_play_count": 0,
    })
    _salvar_historico(historico)


def registrar_feedback(discord_user_id, track_id_alvo, feedback):
    """feedback: "positivo" ou "negativo". Marca a entrada MAIS RECENTE desse
    track_id PARA ESSA PESSOA - se a mesma música foi recomendada mais de uma
    vez, o feedback é sobre a aparição mais recente."""
    discord_user_id = str(discord_user_id)
    historico = carregar_historico()
    for entrada in reversed(historico):
        if entrada.get("discord_user_id") == discord_user_id and entrada["track_id"] == track_id_alvo:
            entrada["user_feedback"] = feedback
            _salvar_historico(historico)
            return entrada
    return None


def obter_historico(discord_user_id, limite=20):
    return list(reversed(_do_usuario(carregar_historico(), discord_user_id)))[:limite]


def _mais_recentes_por_track(entradas):
    """Uma entrada por `track_id`, mantendo a MAIS RECENTE (histórico já vem em
    ordem cronológica de inserção - a última aparição de cada track_id vence)."""
    por_track = {}
    for entrada in entradas:
        por_track[entrada["track_id"]] = entrada
    return list(por_track.values())


def obter_aprovadas(discord_user_id):
    entradas = _mais_recentes_por_track(_do_usuario(carregar_historico(), discord_user_id))
    return [e for e in entradas if e.get("user_feedback") == "positivo"]


def obter_desaprovadas(discord_user_id):
    entradas = _mais_recentes_por_track(_do_usuario(carregar_historico(), discord_user_id))
    return [e for e in entradas if e.get("user_feedback") == "negativo"]


def foi_votada(discord_user_id, titulo, artista):
    """Diferente de tocada/apresentada - só conta quem recebeu VOTO de
    verdade (👍 ou 👎), olhando a aparição mais recente (mesmo critério de
    `obter_aprovadas`/`obter_desaprovadas`). Usada pelo pool (`pool.py`)
    pra decidir quem sai de lá - pedido do usuário 2026-08-26: "Musicas sem
    voto não saem do pool" (tocar sem avaliar não é sinal de rejeição nem
    de aprovação, então não deveria remover a música do repertório)."""
    id_alvo = track_id(titulo, artista)
    entradas = _mais_recentes_por_track(_do_usuario(carregar_historico(), discord_user_id))
    entrada = next((e for e in entradas if e["track_id"] == id_alvo), None)
    return bool(entrada and entrada.get("user_feedback") in ("positivo", "negativo"))


def obter_voto(discord_user_id, titulo, artista):
    """Devolve `"positivo"`/`"negativo"`/`None` (a aparição mais recente,
    mesmo critério de `foi_votada`) - usado pelo ERIS pra mostrar "(👍)"/
    "(👎)" na mensagem de "tocando agora" quando a faixa já foi avaliada
    antes por quem iniciou a sessão (2026-08-27, pedido do usuário)."""
    id_alvo = track_id(titulo, artista)
    entradas = _mais_recentes_por_track(_do_usuario(carregar_historico(), discord_user_id))
    entrada = next((e for e in entradas if e["track_id"] == id_alvo), None)
    return entrada.get("user_feedback") if entrada else None


# --------------------------------------------------------------------------
# Eventos de escuta passivos (2026-08-26, pedido do usuário: "Registrar
# eventos passivos úteis... mesmo quando o evento não alterar imediatamente o
# perfil") - log BRUTO de todo evento de reprodução (fração tocada, se foi
# pulada, em que momento), separado do histórico de recomendações - guarda
# dado mesmo quando não gera ajuste de peso nenhum, pra poder refinar o
# algoritmo depois sem ter perdido a informação.
# --------------------------------------------------------------------------

def _carregar_eventos():
    if not os.path.exists(ARQUIVO_EVENTOS_ESCUTA):
        return []
    try:
        with open(ARQUIVO_EVENTOS_ESCUTA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _salvar_eventos(eventos):
    os.makedirs(os.path.dirname(ARQUIVO_EVENTOS_ESCUTA), exist_ok=True)
    with open(ARQUIVO_EVENTOS_ESCUTA, "w", encoding="utf-8") as f:
        json.dump(eventos, f, ensure_ascii=False, indent=2)


def registrar_evento_escuta(discord_user_id, titulo, artista, fracao_tocada, pulado, momento_do_skip=None):
    eventos = _carregar_eventos()
    eventos.append({
        "discord_user_id": str(discord_user_id),
        "track_id": track_id(titulo, artista),
        "titulo": titulo,
        "artista": artista,
        "fracao_tocada": fracao_tocada,
        "pulado": bool(pulado),
        "momento_do_skip_segundos": momento_do_skip,
        "registrado_em": date.today().isoformat(),
    })
    _salvar_eventos(eventos)


def contar_eventos_fracos_recentes(discord_user_id, artista, negativo, limite_eventos=10):
    """Quantos dos últimos `limite_eventos` de um artista, pra essa pessoa, são
    sinais fracos na direção pedida (`negativo=True` conta skips <25%;
    `negativo=False` conta faixas ouvidas >75%/até o fim) - usado por
    `feedback.py` pra só ajustar peso depois de um padrão consistente, não
    num evento isolado."""
    discord_user_id = str(discord_user_id)
    artista_normalizado = artista.strip().lower()
    eventos = [
        e for e in _carregar_eventos()
        if e["discord_user_id"] == discord_user_id and e["artista"].strip().lower() == artista_normalizado
    ]
    eventos_do_artista = eventos[-limite_eventos:]
    if negativo:
        return sum(1 for e in eventos_do_artista if e["pulado"] and e["fracao_tocada"] is not None and e["fracao_tocada"] < 0.25)
    return sum(1 for e in eventos_do_artista if not e["pulado"] or (e["fracao_tocada"] is not None and e["fracao_tocada"] > 0.75))

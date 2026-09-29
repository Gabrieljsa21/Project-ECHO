# -*- coding: utf-8 -*-
"""Pontuação por artista (2026-09-26, pedido do usuário: "cada artista ter uma
pontuação, e cada curtida influenciar nela. Mas ao mesmo tempo não quero
matar um artista completamente após 1 deslike").

Cada artista tem, por pessoa, uma nota de -1 (rejeitado) a +1 (adora):

- 👍 sobe a nota com retorno decrescente (`+0.25 * (1 - nota)`);
- 👎 desce um passo fixo (`-0.2`), sem nunca chegar a -1 sozinho.

A nota entra no ranking (`recomendador.py`) e no sorteio do pool
(`pool.py`) na hora - uma curtida de agora já muda o que toca agora, sem
esperar a próxima geração do pool.

Regra das 5 chances: um 👎 num artista SEM nenhuma curtida (e que não é
favorito cadastrado) coloca ele "em prova". O ECHO separa as 5 faixas mais
populares dele (Last.fm) e vai intercalando no Caos/continuação, no máximo
uma a cada `INTERVALO_PROVA` sugestões. Só 👎 explícito gasta chance
(decisão do usuário: pular ou ouvir sem votar não conta). Qualquer 👍 do
artista encerra a prova e ele volta ao normal. Se as 5 levarem 👎, ele vira
"rejeitado" e sai das recomendações de vez (decisão do usuário: rejeição
permanente) - só volta se o próprio usuário curtir uma música dele, por
exemplo achada na busca.

Uma faixa de prova servida `MAX_VEZES_SERVIDA` vezes deixa de ser servida,
mas ainda aceita 👎 (pode estar tocando agora). No ciclo seguinte, se só
sobrarem faixas assim, a prova termina como neutra e o artista volta ao
normal - senão uma faixa que o usuário só ouve sem votar voltaria para
sempre. Rejeição exige 👎 em TODAS as faixas da prova.

A 1ª leitura de cada pessoa reconstrói as notas a partir dos votos que já
existem no histórico, sem abrir prova nenhuma (votos antigos não disparam a
regra retroativamente)."""
import json
import os
import threading
from datetime import date

from echo.core import historico as historico_mod
from echo.core import perfil as perfil_mod
from echo.providers import ProvedorIndisponivel

ARQUIVO_ARTISTAS = "data/artistas.json"

NOTA_MINIMA = -1.0
NOTA_MAXIMA = 1.0
FATOR_CURTIDA = 0.25
PASSO_DESCURTIDA = 0.2
NOTA_FAVORITO = 1.0  # favorito cadastrado sem voto nenhum: mesmo bônus de antes (compatibilidade +0.4)

FAIXAS_NA_PROVA = 5
FAIXAS_BUSCADAS_NA_PROVA = 15  # busca mais que 5 pra ainda ter 5 depois de tirar as já votadas
INTERVALO_PROVA = 5  # sugestões entre uma faixa de prova e outra
MAX_VEZES_SERVIDA = 2

ESTADO_NORMAL = "normal"
ESTADO_EM_PROVA = "em_prova"
ESTADO_REJEITADO = "rejeitado"

_lock = threading.Lock()


def _chave(nome):
    return nome.strip().lower()


def _carregar_todos():
    if not os.path.exists(ARQUIVO_ARTISTAS):
        return {}
    try:
        with open(ARQUIVO_ARTISTAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_todos(todos):
    os.makedirs(os.path.dirname(ARQUIVO_ARTISTAS), exist_ok=True)
    with open(ARQUIVO_ARTISTAS, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def _registro_vazio(nome):
    return {
        "nome": nome,
        "nota": 0.0,
        "curtidas": 0,
        "descurtidas": 0,
        "estado": ESTADO_NORMAL,
        "prova": [],
        "reprovadas_na_prova": 0,
        "total_na_prova": 0,
        "atualizado_em": date.today().isoformat(),
    }


def _aplicar_curtida(registro):
    registro["nota"] = min(NOTA_MAXIMA, registro["nota"] + FATOR_CURTIDA * (1 - registro["nota"]))
    registro["curtidas"] += 1


def _aplicar_descurtida(registro):
    # Nunca chega a -1 só por descurtidas soltas - -1 é exclusivo da rejeição.
    registro["nota"] = max(NOTA_MINIMA + PASSO_DESCURTIDA, registro["nota"] - PASSO_DESCURTIDA)
    registro["descurtidas"] += 1


def _reconstruir_do_historico(discord_user_id):
    """Notas iniciais a partir dos votos já registrados, na ordem em que
    aconteceram. Não abre prova: a regra das 5 chances só vale daqui pra
    frente."""
    usuario = {"artistas": {}, "sugestoes_desde_prova": 0}
    for entrada in historico_mod._mais_recentes_por_track(historico_mod._do_usuario(historico_mod.carregar_historico(), discord_user_id)):
        voto = entrada.get("user_feedback")
        if voto not in ("positivo", "negativo"):
            continue
        registro = usuario["artistas"].setdefault(_chave(entrada["artista"]), _registro_vazio(entrada["artista"]))
        if voto == "positivo":
            _aplicar_curtida(registro)
        else:
            _aplicar_descurtida(registro)
    return usuario


def _usuario(todos, discord_user_id):
    chave = str(discord_user_id)
    if chave not in todos:
        todos[chave] = _reconstruir_do_historico(discord_user_id)
    todos[chave].setdefault("artistas", {})
    todos[chave].setdefault("sugestoes_desde_prova", 0)
    return todos[chave]


def carregar(discord_user_id):
    """`{chave_do_artista: registro}` dessa pessoa."""
    with _lock:
        todos = _carregar_todos()
        novo = str(discord_user_id) not in todos
        usuario = _usuario(todos, discord_user_id)
        if novo:
            _salvar_todos(todos)
        return usuario["artistas"]


def _eh_favorito(discord_user_id, nome):
    perfil = perfil_mod.carregar_perfil(discord_user_id)
    return any(_chave(a["nome"]) == _chave(nome) for a in perfil["favorite_artists"])


def nota_efetiva(discord_user_id, nome, artistas=None, perfil=None):
    """Nota usada no ranking. Sem registro: 1.0 pra favorito cadastrado,
    0.0 pro resto. `artistas`/`perfil` já carregados evitam reler arquivo
    em laço."""
    artistas = artistas if artistas is not None else carregar(discord_user_id)
    registro = artistas.get(_chave(nome))
    if registro is not None:
        return registro["nota"]
    perfil = perfil if perfil is not None else perfil_mod.carregar_perfil(discord_user_id)
    if any(_chave(a["nome"]) == _chave(nome) for a in perfil["favorite_artists"]):
        return NOTA_FAVORITO
    return 0.0


def esta_rejeitado(discord_user_id, nome, artistas=None):
    artistas = artistas if artistas is not None else carregar(discord_user_id)
    registro = artistas.get(_chave(nome))
    return bool(registro and registro["estado"] == ESTADO_REJEITADO)


def _abrir_prova(registro, provedor, discord_user_id, titulo_descurtido):
    """Separa as `FAIXAS_NA_PROVA` mais populares (ignorando a que acabou de
    levar 👎 e as já curtidas). As que já tinham 👎 contam como chance gasta.
    Sem provedor disponível, a prova não abre agora - tenta de novo no
    próximo 👎."""
    try:
        faixas = provedor.obter_faixas_do_artista(registro["nome"], limite=FAIXAS_BUSCADAS_NA_PROVA)
    except ProvedorIndisponivel:
        return
    except Exception:
        return
    id_descurtido = historico_mod.track_id(titulo_descurtido, registro["nome"])
    selecionadas = []
    for faixa in faixas:
        id_faixa = historico_mod.track_id(faixa["titulo"], faixa["artista"])
        if id_faixa == id_descurtido or any(s["id"] == id_faixa for s in selecionadas):
            continue
        voto = historico_mod.obter_voto(discord_user_id, faixa["titulo"], faixa["artista"])
        if voto == "positivo":
            continue
        selecionadas.append({"id": id_faixa, "titulo": faixa["titulo"], "artista": faixa["artista"], "voto": voto})
        if len(selecionadas) == FAIXAS_NA_PROVA:
            break
    if not selecionadas:
        return
    registro["estado"] = ESTADO_EM_PROVA
    registro["total_na_prova"] = len(selecionadas)
    registro["reprovadas_na_prova"] = sum(1 for s in selecionadas if s["voto"] == "negativo")
    registro["prova"] = [
        {"titulo": s["titulo"], "artista": s["artista"], "vezes_servida": 0}
        for s in selecionadas if s["voto"] != "negativo"
    ]
    _encerrar_prova_se_acabou(registro)


def _encerrar_prova_se_acabou(registro):
    """Sem faixa pendente: rejeitado se TODAS foram reprovadas, senão volta
    ao normal."""
    if registro["estado"] != ESTADO_EM_PROVA or registro["prova"]:
        return
    if registro["reprovadas_na_prova"] >= registro.get("total_na_prova", FAIXAS_NA_PROVA):
        registro["estado"] = ESTADO_REJEITADO
        registro["nota"] = NOTA_MINIMA
    else:
        registro["estado"] = ESTADO_NORMAL
    registro["reprovadas_na_prova"] = 0
    registro["total_na_prova"] = 0


def _encerrar_por_neutras(registro):
    """Só sobraram faixas já servidas o máximo de vezes, sem voto: a prova
    termina sem rejeitar."""
    if registro["estado"] == ESTADO_EM_PROVA and registro["prova"] and all(
        f["vezes_servida"] >= MAX_VEZES_SERVIDA for f in registro["prova"]
    ):
        registro["prova"] = []
        registro["estado"] = ESTADO_NORMAL
        registro["reprovadas_na_prova"] = 0
        registro["total_na_prova"] = 0


def registrar_voto(discord_user_id, titulo, artista, feedback, provedor=None, abrir_prova=True):
    """Atualiza a nota/estado do artista com um 👍/👎. `abrir_prova=False`
    (importação de votos antigos) só mexe na nota. Devolve o registro."""
    with _lock:
        todos = _carregar_todos()
        usuario = _usuario(todos, discord_user_id)
        registro = usuario["artistas"].setdefault(_chave(artista), _registro_vazio(artista))
        id_faixa = historico_mod.track_id(titulo, artista)

        if feedback == "positivo":
            _aplicar_curtida(registro)
            if registro["estado"] != ESTADO_NORMAL:
                registro["estado"] = ESTADO_NORMAL
                registro["prova"] = []
                registro["reprovadas_na_prova"] = 0
        elif feedback == "negativo":
            _aplicar_descurtida(registro)
            if registro["estado"] == ESTADO_EM_PROVA:
                antes = len(registro["prova"])
                registro["prova"] = [f for f in registro["prova"] if historico_mod.track_id(f["titulo"], f["artista"]) != id_faixa]
                if len(registro["prova"]) < antes:
                    registro["reprovadas_na_prova"] += 1
                _encerrar_prova_se_acabou(registro)
            elif (
                registro["estado"] == ESTADO_NORMAL and abrir_prova and provedor is not None
                and registro["curtidas"] == 0 and not _eh_favorito(discord_user_id, artista)
            ):
                _abrir_prova(registro, provedor, discord_user_id, titulo)

        registro["atualizado_em"] = date.today().isoformat()
        _salvar_todos(todos)
        return dict(registro)


def proxima_faixa_de_prova(discord_user_id, excluidos=None):
    """Chamado a cada sugestão do Caos/continuação. Conta as sugestões e, a
    cada `INTERVALO_PROVA`, devolve uma faixa pendente de algum artista em
    prova (a menos servida primeiro) - `None` no resto das vezes."""
    excluidos = {e.lower() for e in (excluidos or [])}
    with _lock:
        todos = _carregar_todos()
        usuario = _usuario(todos, discord_user_id)
        usuario["sugestoes_desde_prova"] += 1
        escolhida = None
        if usuario["sugestoes_desde_prova"] >= INTERVALO_PROVA:
            for registro in usuario["artistas"].values():
                _encerrar_por_neutras(registro)
            pendentes = [
                (faixa, registro)
                for registro in usuario["artistas"].values() if registro["estado"] == ESTADO_EM_PROVA
                for faixa in registro["prova"]
                if faixa["vezes_servida"] < MAX_VEZES_SERVIDA
                and historico_mod.track_id(faixa["titulo"], faixa["artista"]) not in excluidos
            ]
            if pendentes:
                faixa, registro = min(pendentes, key=lambda par: par[0]["vezes_servida"])
                faixa["vezes_servida"] += 1
                escolhida = {
                    "titulo": faixa["titulo"], "artista": faixa["artista"], "generos": [],
                    "_score": 0.0, "_categoria": "prova", "origem": "prova",
                }
                usuario["sugestoes_desde_prova"] = 0
        _salvar_todos(todos)
    if escolhida:
        historico_mod.registrar_recomendacao(discord_user_id, escolhida["titulo"], escolhida["artista"], reason="prova", category="prova")
    return escolhida


def detalhes(discord_user_id, provedor, nome, limite=10):
    """Tela de artista do SIREN (2026-09-26): nota/estado dessa pessoa +
    faixas mais populares no provedor (vazio se o provedor falhar - a nota
    continua útil sozinha)."""
    try:
        populares = provedor.obter_faixas_do_artista(nome, limite=limite)
    except ProvedorIndisponivel:
        populares = []
    except Exception:
        populares = []
    registro = carregar(discord_user_id).get(_chave(nome))
    return {
        "nome": populares[0]["artista"] if populares else nome,
        "nota": nota_efetiva(discord_user_id, nome),
        "estado": registro["estado"] if registro else ESTADO_NORMAL,
        "curtidas": registro["curtidas"] if registro else 0,
        "descurtidas": registro["descurtidas"] if registro else 0,
        "populares": [
            {"titulo": f["titulo"], "artista": f["artista"], "popularidade": f.get("popularidade")}
            for f in populares
        ],
    }


def resumo(discord_user_id):
    """Lista ordenada por nota (maior primeiro) - rota `/perfil/artistas`."""
    return sorted(carregar(discord_user_id).values(), key=lambda r: r["nota"], reverse=True)

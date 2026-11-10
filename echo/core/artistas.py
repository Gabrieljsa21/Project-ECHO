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
from datetime import date

from echo.core import armazenamento
from echo.core import historico as historico_mod
from echo.core import perfil as perfil_mod
from echo.core import versoes as versoes_mod
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

_lock = armazenamento.LOCK

# Contagem de sugestões desde a última faixa de prova, por pessoa. Fica em
# memória (2026-11-09): gravar o arquivo a cada sugestão só para subir esse
# número regravava `artistas.json` inteiro a cada faixa do Caos. O valor do
# arquivo serve de ponto de partida depois de reiniciar.
_sugestoes_desde_prova = {}


def _chave(nome):
    return nome.strip().lower()


def _carregar_todos():
    return armazenamento.carregar(ARQUIVO_ARTISTAS, dict)


def _salvar_todos(todos):
    armazenamento.salvar(ARQUIVO_ARTISTAS, todos)


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
    for entrada in historico_mod._indice(discord_user_id)["mais_recentes"]:
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


def _buscar_faixas_para_prova(provedor, nome):
    try:
        return provedor.obter_faixas_do_artista(nome, limite=FAIXAS_BUSCADAS_NA_PROVA)
    except ProvedorIndisponivel:
        return None
    except Exception:
        return None


def _pode_abrir_prova(registro, discord_user_id, artista):
    return (
        registro["estado"] == ESTADO_NORMAL and registro["curtidas"] == 0
        and not _eh_favorito(discord_user_id, artista) and not versoes_mod.eh_derivada(artista)
    )


def _abrir_prova(registro, faixas, discord_user_id, titulo_descurtido):
    """Separa as `FAIXAS_NA_PROVA` mais populares (ignorando a que acabou de
    levar 👎 e as já curtidas). As que já tinham 👎 contam como chance gasta.
    `faixas` vem de `_buscar_faixas_para_prova`, chamada fora da trava; sem
    provedor disponível (`None`), a prova não abre agora - tenta de novo no
    próximo 👎."""
    if not faixas:
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
    # A busca das faixas da prova é rede: fica fora da trava (2026-11-09),
    # pra um voto não segurar os outros pedidos enquanto o Last.fm responde.
    faixas_prova = None
    if feedback == "negativo" and abrir_prova and provedor is not None:
        registro_atual = carregar(discord_user_id).get(_chave(artista)) or _registro_vazio(artista)
        if _pode_abrir_prova(registro_atual, discord_user_id, artista):
            faixas_prova = _buscar_faixas_para_prova(provedor, registro_atual["nome"])

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
            elif abrir_prova and provedor is not None and _pode_abrir_prova(registro, discord_user_id, artista):
                _abrir_prova(registro, faixas_prova, discord_user_id, titulo)

        registro["atualizado_em"] = date.today().isoformat()
        _salvar_todos(todos)
        return dict(registro)


def desfazer_voto(discord_user_id, artista, feedback):
    """Inverso de `registrar_voto` (voto retirado ou trocado no SIREN,
    2026-10-12): devolve a nota ao valor de antes do voto e desconta a
    contagem. Os limites da nota podem deixar uma pequena diferença. Não
    mexe no estado de prova: uma prova aberta segue o curso normal."""
    with _lock:
        todos = _carregar_todos()
        usuario = _usuario(todos, discord_user_id)
        registro = usuario["artistas"].get(_chave(artista))
        if registro is None:
            return None
        if feedback == "positivo" and registro["curtidas"] > 0:
            registro["nota"] = max(NOTA_MINIMA, (registro["nota"] - FATOR_CURTIDA) / (1 - FATOR_CURTIDA))
            registro["curtidas"] -= 1
        elif feedback == "negativo" and registro["descurtidas"] > 0:
            if registro["estado"] != ESTADO_REJEITADO:
                registro["nota"] = min(NOTA_MAXIMA, registro["nota"] + PASSO_DESCURTIDA)
            registro["descurtidas"] -= 1
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
        novo = str(discord_user_id) not in todos
        usuario = _usuario(todos, discord_user_id)
        chave_contagem = (ARQUIVO_ARTISTAS, str(discord_user_id))
        contagem = _sugestoes_desde_prova.get(chave_contagem, usuario["sugestoes_desde_prova"]) + 1
        _sugestoes_desde_prova[chave_contagem] = contagem
        mudou = novo
        escolhida = None
        if contagem >= INTERVALO_PROVA:
            for registro in usuario["artistas"].values():
                estado_antes = registro["estado"]
                _encerrar_por_neutras(registro)
                mudou = mudou or registro["estado"] != estado_antes
            pendentes = [
                (faixa, registro)
                for registro in usuario["artistas"].values()
                if registro["estado"] == ESTADO_EM_PROVA and not versoes_mod.eh_derivada(registro["nome"])
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
                _sugestoes_desde_prova[chave_contagem] = 0
                mudou = True
        if mudou:
            usuario["sugestoes_desde_prova"] = _sugestoes_desde_prova[chave_contagem]
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

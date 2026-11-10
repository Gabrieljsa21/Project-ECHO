# -*- coding: utf-8 -*-
"""Histórico de recomendações do Radar Musical (seção 8 do ECHO_SPEC) - evita
repetição desnecessária e guarda o feedback de cada faixa recomendada. Permite
redescoberta só depois de `DIAS_REDESCOBERTA` (seção 9), nunca reaparece só porque
continua popular.

🔥 Por pessoa (2026-08-26) - toda entrada agora carrega `discord_user_id`, e toda
função de consulta/escrita exige isso como parâmetro (mesmo motivo de
`perfil.py`: Modo Música é social, feedback de um visitante não pode contar
como se fosse do dono)."""
import functools
import os
import re
import shutil
from datetime import date, timedelta

from echo.core import armazenamento

ARQUIVO_HISTORICO = "data/historico_recomendacoes.json"
ARQUIVO_EVENTOS_ESCUTA = "data/eventos_escuta.json"
DIAS_REDESCOBERTA = 90


def track_id(titulo, artista):
    return f"{artista.strip().lower()}::{titulo.strip().lower()}"


def carregar_historico():
    """Lista em cache (`armazenamento`): não alterar fora das funções deste
    módulo, que sempre gravam logo depois de mexer."""
    return armazenamento.carregar(ARQUIVO_HISTORICO, list, cache=True)


def _salvar_historico(historico):
    armazenamento.salvar(ARQUIVO_HISTORICO, historico, cache=True)


def _do_usuario(historico, discord_user_id):
    discord_user_id = str(discord_user_id)
    return [e for e in historico if e.get("discord_user_id") == discord_user_id]


_indices = {}  # discord_user_id -> (versão do arquivo, índice)


def _indice(discord_user_id):
    """Índice do histórico de uma pessoa, refeito só quando o arquivo muda
    (2026-11-09). Antes cada consulta relia e varria o arquivo inteiro, e o
    ranking faz uma consulta por candidato.

    - `mais_recentes`: resultado de `_mais_recentes_por_track`;
    - `por_track`: o mesmo, por `track_id`;
    - `ultima_recomendacao`: data ISO mais recente de cada `track_id`."""
    discord_user_id = str(discord_user_id)
    with armazenamento.LOCK:
        historico = carregar_historico()
        chave = (ARQUIVO_HISTORICO, armazenamento.versao(ARQUIVO_HISTORICO))
        guardado = _indices.get(discord_user_id)
        if guardado is not None and guardado[0] == chave:
            return guardado[1]
        entradas = _do_usuario(historico, discord_user_id)
        mais_recentes = _mais_recentes_por_track(entradas)
        ultima = {}
        for entrada in entradas:
            if entrada["recommended_at"] > ultima.get(entrada["track_id"], ""):
                ultima[entrada["track_id"]] = entrada["recommended_at"]
        indice = {
            "mais_recentes": mais_recentes,
            "por_track": {e["track_id"]: e for e in mais_recentes},
            "ultima_recomendacao": ultima,
        }
        _indices[discord_user_id] = (chave, indice)
        return indice


def foi_recomendada_recentemente(discord_user_id, titulo, artista, dias=DIAS_REDESCOBERTA):
    """Dedup de 90 dias (Radar semanal) - por pessoa."""
    ultima = _indice(discord_user_id)["ultima_recomendacao"].get(track_id(titulo, artista))
    return bool(ultima and ultima >= (date.today() - timedelta(days=dias)).isoformat())


def registrar_recomendacao(discord_user_id, titulo, artista, reason, category):
    """Registra uma aparição da faixa. Se a entrada mais recente dela ainda
    não tem voto, essa entrada é atualizada (data, motivo, `aparicoes` + 1)
    e vai para o fim da lista, em vez de nascer uma linha nova a cada vez
    que a faixa toca (2026-11-09: 87% do arquivo eram repetições sem voto
    do pool). Entrada com voto nunca é alterada aqui."""
    discord_user_id = str(discord_user_id)
    id_alvo = track_id(titulo, artista)
    hoje = date.today().isoformat()
    with armazenamento.LOCK:
        historico = carregar_historico()
        for posicao in range(len(historico) - 1, -1, -1):
            entrada = historico[posicao]
            if entrada.get("discord_user_id") != discord_user_id or entrada["track_id"] != id_alvo:
                continue
            if not entrada.get("user_feedback"):
                del historico[posicao]
                entrada["recommended_at"] = hoje
                entrada["reason"] = reason
                entrada["category"] = category
                entrada["aparicoes"] = entrada.get("aparicoes", 1) + 1
                historico.append(entrada)
                _salvar_historico(historico)
                return
            break
        historico.append({
            "discord_user_id": discord_user_id,
            "track_id": id_alvo,
            "titulo": titulo,
            "artista": artista,
            "recommended_at": hoje,
            "reason": reason,
            "category": category,
            "user_feedback": None,
            "subsequent_play_count": 0,
            "aparicoes": 1,
        })
        _salvar_historico(historico)


def compactar():
    """Junta as repetições já gravadas: por pessoa e faixa ficam a entrada
    mais recente com voto e a mais recente de todas (se for outra). O total
    de aparições vai para a última que fica. Antes de gravar, guarda uma
    cópia do arquivo como `<nome>.antes-compactacao-<data>.json`. Devolve
    quantas entradas saíram."""
    with armazenamento.LOCK:
        historico = carregar_historico()
        grupos = {}
        for posicao, entrada in enumerate(historico):
            grupos.setdefault((entrada.get("discord_user_id"), entrada["track_id"]), []).append(posicao)
        manter = set()
        totais = {}
        for posicoes in grupos.values():
            if len(posicoes) == 1:
                manter.add(posicoes[0])
                continue
            ultima = posicoes[-1]
            manter.add(ultima)
            com_voto = [p for p in posicoes if historico[p].get("user_feedback")]
            if com_voto:
                manter.add(com_voto[-1])
            totais[ultima] = sum(historico[p].get("aparicoes", 1) for p in posicoes)
        removidas = len(historico) - len(manter)
        if not removidas:
            return 0
        if os.path.exists(ARQUIVO_HISTORICO):
            raiz, extensao = os.path.splitext(ARQUIVO_HISTORICO)
            copia = f"{raiz}.antes-compactacao-{date.today().isoformat()}{extensao}"
            if not os.path.exists(copia):
                shutil.copy2(ARQUIVO_HISTORICO, copia)
        for posicao, total in totais.items():
            historico[posicao]["aparicoes"] = total
        historico[:] = [entrada for posicao, entrada in enumerate(historico) if posicao in manter]
        _salvar_historico(historico)
        return removidas


def registrar_feedback(discord_user_id, track_id_alvo, feedback):
    """feedback: "positivo" ou "negativo". Marca a entrada MAIS RECENTE desse
    track_id PARA ESSA PESSOA - se a mesma música foi recomendada mais de uma
    vez, o feedback é sobre a aparição mais recente."""
    discord_user_id = str(discord_user_id)
    with armazenamento.LOCK:
        historico = carregar_historico()
        for entrada in reversed(historico):
            if entrada.get("discord_user_id") == discord_user_id and entrada["track_id"] == track_id_alvo:
                entrada["user_feedback"] = feedback
                _salvar_historico(historico)
                return entrada
        return None


def limpar_feedback(discord_user_id, track_id_alvo):
    """Tira o voto de TODAS as aparições desse track_id para essa pessoa
    (voto retirado ou trocado no SIREN, 2026-10-12). Todas, não só a mais
    recente: com "voto vence aparição" uma entrada antiga ainda valeria.
    Devolve quantas entradas tinham voto."""
    discord_user_id = str(discord_user_id)
    with armazenamento.LOCK:
        historico = carregar_historico()
        limpas = 0
        for entrada in historico:
            if entrada.get("discord_user_id") == discord_user_id and entrada["track_id"] == track_id_alvo and entrada.get("user_feedback"):
                entrada["user_feedback"] = None
                limpas += 1
        if limpas:
            _salvar_historico(historico)
        return limpas


def obter_historico(discord_user_id, limite=20):
    return list(reversed(_do_usuario(carregar_historico(), discord_user_id)))[:limite]


def _mais_recentes_por_track(entradas):
    """Uma entrada por `track_id`: a MAIS RECENTE COM VOTO, ou a mais recente
    de todas se a faixa nunca foi votada (histórico já vem em ordem
    cronológica de inserção).

    🔥 Voto vence aparição (2026-10-05, achado real: "Counting Stars",
    curtida em 08/26, voltou 9x no Caos do SIREN). Antes a última APARIÇÃO
    vencia, então cada vez que o pool tocava de novo uma faixa curtida,
    a entrada nova (sem voto) apagava o 👍 - `foi_votada` virava False, a
    faixa voltava pro pool e saía das aprovadas. Mesmo efeito com 👎."""
    por_track = {}
    for entrada in entradas:
        anterior = por_track.get(entrada["track_id"])
        if anterior is None or entrada.get("user_feedback") or not anterior.get("user_feedback"):
            por_track[entrada["track_id"]] = entrada
    return list(por_track.values())


def obter_aprovadas(discord_user_id):
    return [e for e in _indice(discord_user_id)["mais_recentes"] if e.get("user_feedback") == "positivo"]


@functools.lru_cache(maxsize=50000)
def chave_frouxa(titulo, artista):
    """Mesma música escrita de jeitos diferentes ("À Sua Maneira", "À sua
    maneira (De música ligeira) - Ao Vivo", "Song - feat. X") vira uma chave
    só: sem parênteses/colchetes, sem o trecho depois de " - " ou "feat." e
    sem pontuação. Mesma regra do `chave_repeticao` do SIREN."""
    titulo = re.sub(r"[\(\[].*?[\)\]]", " ", titulo.lower())
    titulo = re.split(r"\s-\s|\bfeat\.?\b|\bft\.?\b", titulo)[0]
    artista_limpo = re.sub(r"[^\w]+", "", artista.lower())
    titulo_limpo = re.sub(r"[^\w]+", "", titulo)
    return f"{artista_limpo}::{titulo_limpo}"


def chaves_frouxas_votadas(discord_user_id):
    """Chaves frouxas de toda faixa com 👍 ou 👎 vigente - variante ao vivo/
    remix de uma música já votada também conta como conhecida."""
    indice = _indice(discord_user_id)
    if "chaves_frouxas_votadas" not in indice:
        indice["chaves_frouxas_votadas"] = frozenset(
            chave_frouxa(e["titulo"], e["artista"]) for e in indice["mais_recentes"]
            if e.get("user_feedback") in ("positivo", "negativo")
        )
    return indice["chaves_frouxas_votadas"]


def obter_desaprovadas(discord_user_id):
    return [e for e in _indice(discord_user_id)["mais_recentes"] if e.get("user_feedback") == "negativo"]


def foi_votada(discord_user_id, titulo, artista):
    """Diferente de tocada/apresentada - só conta quem recebeu VOTO de
    verdade (👍 ou 👎), olhando a aparição mais recente (mesmo critério de
    `obter_aprovadas`/`obter_desaprovadas`). Usada pelo pool (`pool.py`)
    pra decidir quem sai de lá - pedido do usuário 2026-08-26: "Musicas sem
    voto não saem do pool" (tocar sem avaliar não é sinal de rejeição nem
    de aprovação, então não deveria remover a música do repertório)."""
    entrada = _indice(discord_user_id)["por_track"].get(track_id(titulo, artista))
    return bool(entrada and entrada.get("user_feedback") in ("positivo", "negativo"))


def obter_voto(discord_user_id, titulo, artista):
    """Devolve `"positivo"`/`"negativo"`/`None` (a aparição mais recente,
    mesmo critério de `foi_votada`) - usado pelo ERIS pra mostrar "(👍)"/
    "(👎)" na mensagem de "tocando agora" quando a faixa já foi avaliada
    antes por quem iniciou a sessão (2026-08-27, pedido do usuário)."""
    entrada = _indice(discord_user_id)["por_track"].get(track_id(titulo, artista))
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
    return armazenamento.carregar(ARQUIVO_EVENTOS_ESCUTA, list, cache=True)


def _salvar_eventos(eventos):
    armazenamento.salvar(ARQUIVO_EVENTOS_ESCUTA, eventos, cache=True)


def registrar_evento_escuta(discord_user_id, titulo, artista, fracao_tocada, pulado, momento_do_skip=None):
    with armazenamento.LOCK:
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


_indices_eventos = {}  # discord_user_id -> (versão do arquivo, {track_id: data ISO mais recente})


def _ultima_escuta(discord_user_id):
    with armazenamento.LOCK:
        eventos = _carregar_eventos()
        chave = (ARQUIVO_EVENTOS_ESCUTA, armazenamento.versao(ARQUIVO_EVENTOS_ESCUTA))
        guardado = _indices_eventos.get(discord_user_id)
        if guardado is not None and guardado[0] == chave:
            return guardado[1]
        ultima = {}
        for evento in eventos:
            if evento.get("discord_user_id") == discord_user_id and evento["registrado_em"] > ultima.get(evento["track_id"], ""):
                ultima[evento["track_id"]] = evento["registrado_em"]
        _indices_eventos[discord_user_id] = (chave, ultima)
        return ultima


def obter_ultima_aparicao(discord_user_id, track_id_alvo):
    """Data mais recente (recomendada OU realmente ouvida) em que essa faixa
    apareceu pra essa pessoa - usado por `core/redescobertas.py` (seção 9)
    pra saber há quanto tempo ela sumiu da rotação. `None` se nunca apareceu
    em nenhuma das duas fontes."""
    discord_user_id = str(discord_user_id)
    datas = [
        data for data in (
            _indice(discord_user_id)["ultima_recomendacao"].get(track_id_alvo),
            _ultima_escuta(discord_user_id).get(track_id_alvo),
        ) if data
    ]
    return date.fromisoformat(max(datas)) if datas else None


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

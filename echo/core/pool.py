# -*- coding: utf-8 -*-
"""Pool pessoal de candidatos musicais (2026-08-26, pedido do usuário: "prefiro
pré-calcular o repertório do que reconstruir recomendações toda vez que o
comando é executado"). Diferente do Radar semanal (lote FECHADO de 10 músicas
curadas com diversidade pra 1 edição), o pool é um reservatório MAIOR (100-300
por pessoa) que o `/caos`/continuação do ERIS consomem ao vivo - sem chamada de
rede no caminho crítico entre uma faixa acabar e a próxima começar.

Reaproveita a MESMA rodada de descoberta semanal do Radar (`core/radar.py`
chama `gerar_pool_incremental` logo depois de ranquear) - o pool nunca dispara
sozinho uma busca no provedor; quem varre o Last.fm continua sendo só o Radar
(1x/semana) ou a descoberta de emergência em `continuacao.py` (fallback raro).

INCREMENTAL, não recriado do zero (seção pedida pelo usuário: "o pool deve ser
incremental... novas rodadas adicionam candidatos, atualizam scores e removem
entradas inválidas ou obsoletas") - preserva o que ainda não foi consumido
entre uma rodada de descoberta e outra."""
import os
import json
import random
import threading
import time
from datetime import date

from echo.core import historico as historico_mod
from echo.core import recomendador as recomendador_mod
from echo.core import perfil as perfil_mod
from echo.providers import obter_provedor, ProvedorIndisponivel

ARQUIVO_POOL = "data/pool_musical.json"
TAMANHO_ALVO = 200

# 🔥 Reabastecimento proativo em background (2026-08-28, pedido do usuário:
# "/caos deve manter sempre pelo menos 20 músicas disponíveis no pool
# pessoal... quando a quantidade disponível cair abaixo de 20, o ECHO deve
# iniciar em background uma nova pesquisa e tentar adicionar 30 músicas
# inéditas") - achado real que motivou isso: pool de um usuário com só 29
# candidatas (bem abaixo do `TAMANHO_ALVO`=200) fazia o `/caos` esgotar a
# Camada 1 (pool) cedo demais numa sessão longa e ficar preso na Camada 2
# (aprovadas) até a próxima geração semanal do Radar - ver `continuacao.py`.
MINIMO_DISPONIVEL = 20
META_REABASTECIMENTO = 30
LIMITE_SEMENTES_APROVADAS = 40
LIMITE_FAIXAS_POR_SEMENTE = 15

# 🔥 O ECHO é um `HTTPServer` de thread ÚNICA (`api_bridge.py`) - "não
# bloquear nem interromper a reprodução" aqui significa literalmente não
# segurar essa thread enquanto a descoberta faz chamadas de rede. `_lock_
# arquivo` protege o arquivo do pool (agora escrito por até 2 threads ao
# mesmo tempo: a principal, num voto/feedback, e a de reabastecimento).
_lock_arquivo = threading.Lock()
_lock_em_andamento = threading.Lock()
_reabastecendo = set()  # discord_user_id (str) com pesquisa em andamento - evita disparo duplicado

# 🔥 Sorteio entre as TOP N por score, não sempre a 1ª (2026-08-27, achado
# real: com "Musicas sem voto não saem do pool" - `consumir_proxima` parou
# de remover a faixa escolhida do pool - `max()` estrito virou determinístico
# demais: sessões novas (exclusão de sessão vazia) sempre batiam na MESMA
# faixa de maior afinidade toda vez, ex.: "/caos" 3x seguidas sempre
# devolvendo "Duvet - bôa"). `random.choice` entre as top N preserva "prefere
# afinidade alta" sem virar sempre a mesma escolha.
TAMANHO_TOPO_SORTEIO = 5

# 🔥 Boost de proximidade da semente (2026-08-26) - em memória, sem rede: quando
# o ERIS pede "próxima parecida com X", isso favorece o mesmo artista/gênero da
# faixa tocando agora dentro do pool já calculado, sem precisar buscar nada novo.
BOOST_MESMO_ARTISTA = 0.3
BOOST_GENERO_EM_COMUM = 0.15


def _id_candidato(candidato):
    return f"{candidato['artista'].strip().lower()}::{candidato['titulo'].strip().lower()}"


def _carregar_todos():
    if not os.path.exists(ARQUIVO_POOL):
        return {}
    try:
        with open(ARQUIVO_POOL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_todos(todos):
    os.makedirs(os.path.dirname(ARQUIVO_POOL), exist_ok=True)
    with open(ARQUIVO_POOL, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def carregar_pool(discord_user_id):
    return _carregar_todos().get(str(discord_user_id), {}).get("candidatos", [])


def _salvar_pool(discord_user_id, candidatos):
    todos = _carregar_todos()
    todos[str(discord_user_id)] = {
        "candidatos": candidatos,
        "atualizado_em": date.today().isoformat(),
    }
    _salvar_todos(todos)


def pool_vazio_ou_velho(discord_user_id, dias_max=7):
    entrada = _carregar_todos().get(str(discord_user_id))
    if not entrada or not entrada.get("candidatos"):
        return True
    atualizado_em = entrada.get("atualizado_em")
    if not atualizado_em:
        return True
    return (date.today() - date.fromisoformat(atualizado_em)).days > dias_max


def gerar_pool_incremental(discord_user_id, candidatos_ranqueados, tamanho_alvo=TAMANHO_ALVO):
    """Funde o pool existente com os candidatos recém-ranqueados: atualiza score
    de quem já estava lá, adiciona os novos, remove quem já recebeu VOTO
    (`historico.foi_votada` - só sai quem foi avaliado de verdade, pedido do
    usuário 2026-08-26: "Musicas sem voto não saem do pool" - tocar sem
    avaliar não tira a música do repertório). NUNCA recria do zero.

    🔥 Sob `_lock_arquivo` (2026-08-28) - desde o reabastecimento em
    background (`reabastecer_pool`), o arquivo do pool pode ser escrito por
    2 threads ao mesmo tempo; sem isso, um load-modifica-salva concorrente
    perderia a escrita de uma das duas (lost update)."""
    with _lock_arquivo:
        pool_atual = {_id_candidato(c): c for c in carregar_pool(discord_user_id)}

        for candidato in candidatos_ranqueados:
            chave = _id_candidato(candidato)
            if historico_mod.foi_votada(discord_user_id, candidato["titulo"], candidato["artista"]):
                pool_atual.pop(chave, None)
                continue
            entrada_pool = {
                "titulo": candidato["titulo"],
                "artista": candidato["artista"],
                "generos": candidato.get("generos", []),
                "afinidade": candidato["_score"],
                "origem": candidato.get("fonte") or candidato["_categoria"],
                "artista_semente": candidato.get("artista"),
                "descoberto_em": pool_atual.get(chave, {}).get("descoberto_em", date.today().isoformat()),
            }
            pool_atual[chave] = entrada_pool

        # 🔥 Remove quem ficou pra trás demais (score baixo) se o pool passar do
        # alvo - mantém só os mais afins, não deixa crescer sem limite.
        candidatos_finais = sorted(pool_atual.values(), key=lambda c: c["afinidade"], reverse=True)[:tamanho_alvo]
        _salvar_pool(discord_user_id, candidatos_finais)
        return candidatos_finais


def _boost_proximidade(candidato, seed_artista, seed_generos):
    boost = 0.0
    if seed_artista and candidato["artista"].strip().lower() == seed_artista.strip().lower():
        boost += BOOST_MESMO_ARTISTA
    if seed_generos:
        generos_candidato = {g.lower() for g in candidato.get("generos", [])}
        if generos_candidato & {g.lower() for g in seed_generos}:
            boost += BOOST_GENERO_EM_COMUM
    return boost


def _penalidade_diversidade(candidato, penalidades_sessao):
    if not penalidades_sessao:
        return 0.0
    penalidade = penalidades_sessao.get(f"artista::{candidato['artista'].strip().lower()}", 0) * 0.15
    for genero in candidato.get("generos", []):
        penalidade += penalidades_sessao.get(f"genero::{genero.lower()}", 0) * 0.05
    return penalidade


def consumir_proxima(discord_user_id, seed_artista=None, seed_generos=None, excluidos_sessao=None, penalidades_sessao=None):
    """Devolve uma entrada sorteada entre as `TAMANHO_TOPO_SORTEIO` de maior
    score do pool - `None` se o pool estiver vazio (quem chama decide o
    fallback, ver `continuacao.py`). Registra em `historico` (reason="pool",
    sem voto ainda) - alimenta o dedup de 90 dias do Radar semanal e fica
    pronta pra receber um voto depois.

    🔥 NÃO remove do pool (2026-08-26, pedido do usuário: "Musicas sem
    voto não saem do pool") - dedup de CURTO prazo (não repetir na mesma
    sessão) é responsabilidade de `excluidos_sessao`, de quem chama; só sai
    do pool de vez quando recebe um voto de verdade (`feedback.py` chama
    `remover_track`), ou quando uma rodada de descoberta a filtra via
    `historico.foi_votada` em `gerar_pool_incremental`.

    🔥 Dispara reabastecimento em background se sobrar pouco (2026-08-28,
    ver `_acionar_reabastecimento_background`/`reabastecer_pool`) - a
    checagem é sobre `candidatos_validos` (pool JÁ menos o que a sessão tá
    excluindo agora), exatamente o que o usuário pediu como "quantidade
    disponível". Não impede de devolver o que ainda sobrar no pool - só
    garante que uma pesquisa nova já começou pra quando isso acabar."""
    pool = carregar_pool(discord_user_id)
    excluidos_normalizados = {e.lower() for e in (excluidos_sessao or [])}
    candidatos_validos = [c for c in pool if _id_candidato(c) not in excluidos_normalizados]

    if len(candidatos_validos) < MINIMO_DISPONIVEL:
        _acionar_reabastecimento_background(discord_user_id, excluidos_normalizados)

    if not candidatos_validos:
        return None

    candidatos_ordenados = sorted(
        candidatos_validos,
        key=lambda c: c["afinidade"] + _boost_proximidade(c, seed_artista, seed_generos) - _penalidade_diversidade(c, penalidades_sessao),
        reverse=True,
    )
    escolhida = random.choice(candidatos_ordenados[:TAMANHO_TOPO_SORTEIO])
    historico_mod.registrar_recomendacao(discord_user_id, escolhida["titulo"], escolhida["artista"], reason="pool", category=escolhida.get("origem"))
    return escolhida


def remover_track(discord_user_id, titulo, artista):
    """Sai do pool assim que recebe voto (positivo OU negativo) - chamado
    por `feedback.py` em toda avaliação explícita (2026-08-26). Só a FAIXA
    EXATA - um voto numa música nunca mexe em mais nada do mesmo artista
    (2026-08-27, pedido do usuário: "um 👎 em 1 musica n pode condenar
    todas desse artista. Assim como o like n aprova todas tbm, algumas eu
    gosto e outras nao" - `invalidar_relacionados`, que removia o artista
    inteiro num 👎, foi removido por esse mesmo motivo)."""
    with _lock_arquivo:
        pool = carregar_pool(discord_user_id)
        alvo = _id_candidato({"artista": artista, "titulo": titulo})
        pool_filtrado = [c for c in pool if _id_candidato(c) != alvo]
        if len(pool_filtrado) != len(pool):
            _salvar_pool(discord_user_id, pool_filtrado)
        return pool_filtrado


# --------------------------------------------------------------------------
# Reabastecimento de emergência (2026-08-28) - dispara quando `consumir_
# proxima` percebe que sobrou pouca candidata sem voto pra sessão atual (ver
# `MINIMO_DISPONIVEL` acima). Roda numa THREAD separada porque o ECHO é um
# `HTTPServer` de thread única (`api_bridge.py`) - sem isso, a pesquisa (rede,
# vários segundos) travaria toda resposta do ECHO até terminar, inclusive pro
# `/caos` que só quer consumir o que já sobrou no pool AGORA.
# --------------------------------------------------------------------------

def _acionar_reabastecimento_background(discord_user_id, excluidos_sessao):
    """Impede pesquisa duplicada pro MESMO usuário (pedido explícito) -
    `_reabastecendo` guarda quem já tem uma rodada em andamento; chamadas
    repetidas de `consumir_proxima` enquanto isso (bem comum - o ERIS chama
    isso várias vezes seguidas reabastecendo `fila_logica`) só disparam UMA
    thread, não uma por chamada."""
    discord_user_id = str(discord_user_id)
    with _lock_em_andamento:
        if discord_user_id in _reabastecendo:
            return
        _reabastecendo.add(discord_user_id)
    thread = threading.Thread(
        target=_reabastecer_pool_thread, args=(discord_user_id, set(excluidos_sessao or [])), daemon=True,
    )
    thread.start()


def _reabastecer_pool_thread(discord_user_id, excluidos_sessao):
    try:
        reabastecer_pool(discord_user_id, excluidos_sessao)
    finally:
        with _lock_em_andamento:
            _reabastecendo.discard(discord_user_id)


def _sementes_das_aprovadas(discord_user_id):
    """Artistas únicos das músicas aprovadas (👍) dessa pessoa - a "base"
    pedida pelo usuário pra descoberta de emergência ("usando as músicas
    aprovadas do usuário como base para a descoberta"), mais recente
    primeiro (feedback recente é o sinal mais forte do gosto atual)."""
    aprovadas = historico_mod.obter_aprovadas(discord_user_id)
    vistas = set()
    sementes = []
    for entrada in reversed(aprovadas):
        nome = entrada["artista"].strip()
        chave = nome.lower()
        if chave and chave not in vistas:
            vistas.add(chave)
            sementes.append(nome)
    return sementes[:LIMITE_SEMENTES_APROVADAS]


def _id_dedup_descoberta(candidato):
    """ID da plataforma quando o provedor der um (Last.fm: `url_lastfm`,
    único por faixa) - fallback pra título normalizado + artista quando não
    tiver (pedido explícito do usuário: "Deduplicar por ID da plataforma e,
    como fallback, por título normalizado + artista")."""
    return candidato.get("url_lastfm") or _id_candidato(candidato)


def reabastecer_pool(discord_user_id, excluidos_sessao=None, meta=META_REABASTECIMENTO):
    """Descoberta de emergência síncrona (chamada SÓ dentro da thread de
    `_acionar_reabastecimento_background` - nunca direto do caminho ao vivo).
    Semeada pelos ARTISTAS das aprovadas (não o perfil geral de favoritos/
    gêneros, que já é a fonte do Radar semanal) - "usar as músicas e os
    artistas aprovados... como sementes" foi pedido explicitamente pra ser
    uma fonte DIFERENTE da rodada semanal, não uma repetição dela.

    Incorpora candidatas ao pool a cada semente resolvida, não só no final
    ("adicionar... sem esperar a pesquisa inteira terminar") - uma sessão
    presa na Camada 2 (aprovadas) já pode voltar a consumir do pool assim
    que a primeira leva entrar, sem esperar todas as sementes."""
    inicio = time.monotonic()
    print(f" [ECHO] Reabastecimento de pool iniciado (usuário {discord_user_id}, meta {meta} novas).")
    try:
        provedor = obter_provedor()
    except Exception as e:
        print(f" [ECHO] Reabastecimento abortado (usuário {discord_user_id}) - provedor indisponível: {e}")
        return

    sementes = _sementes_das_aprovadas(discord_user_id)
    if not sementes:
        print(f" [ECHO] Reabastecimento abortado (usuário {discord_user_id}) - ainda sem nenhuma música aprovada pra servir de semente.")
        return

    excluidos_sessao_normalizados = {e.lower() for e in (excluidos_sessao or [])}
    ids_no_pool = {_id_candidato(c) for c in carregar_pool(discord_user_id)}
    ids_ja_vistos_na_rodada = set()  # dedup entre sementes (2 artistas podem devolver a mesma faixa em feat.)
    perfil = perfil_mod.carregar_perfil(discord_user_id)

    analisadas = 0
    descartadas = 0
    adicionadas = 0

    for artista in sementes:
        if adicionadas >= meta:
            break
        try:
            candidatos_brutos = provedor.obter_faixas_do_artista(artista, limite=LIMITE_FAIXAS_POR_SEMENTE)
        except ProvedorIndisponivel:
            continue

        novos_validos = []
        for candidato in candidatos_brutos:
            analisadas += 1
            id_dedup = _id_dedup_descoberta(candidato)
            id_pool = _id_candidato(candidato)
            ja_conhecida = (
                id_dedup in ids_ja_vistos_na_rodada
                or id_pool in ids_no_pool
                or id_pool in excluidos_sessao_normalizados
                or historico_mod.foi_votada(discord_user_id, candidato["titulo"], candidato["artista"])
            )
            if ja_conhecida:
                descartadas += 1
                continue
            novos_validos.append(candidato)
            ids_ja_vistos_na_rodada.add(id_dedup)

        if not novos_validos:
            continue

        # 🔥 Prioriza faixas ainda não avaliadas (pedido explícito) - o
        # próprio ranqueamento já embute isso: `historico.foi_votada` acima
        # já tirou as avaliadas, `ranquear` só ordena por afinidade entre o
        # que sobrou, mesmo motor determinístico do Radar/pool normal.
        ranqueados = recomendador_mod.ranquear(discord_user_id, novos_validos, perfil)
        if not ranqueados:
            descartadas += len(novos_validos)
            continue

        with _lock_arquivo:
            pool_atual = {_id_candidato(c): c for c in carregar_pool(discord_user_id)}
            for candidato in ranqueados:
                if adicionadas >= meta:
                    break
                chave = _id_candidato(candidato)
                pool_atual[chave] = {
                    "titulo": candidato["titulo"],
                    "artista": candidato["artista"],
                    "generos": candidato.get("generos", []),
                    "afinidade": candidato["_score"],
                    "origem": "reabastecimento_aprovadas",
                    "artista_semente": artista,
                    "descoberto_em": date.today().isoformat(),
                }
                ids_no_pool.add(chave)
                adicionadas += 1
            candidatos_finais = sorted(pool_atual.values(), key=lambda c: c["afinidade"], reverse=True)[:TAMANHO_ALVO]
            _salvar_pool(discord_user_id, candidatos_finais)

    duracao = time.monotonic() - inicio
    print(
        f" [ECHO] Reabastecimento de pool concluído em {duracao:.1f}s (usuário {discord_user_id}): "
        f"{analisadas} analisadas, {descartadas} descartadas, {adicionadas} adicionadas."
    )

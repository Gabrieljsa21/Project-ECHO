# -*- coding: utf-8 -*-
"""Processa feedback do Radar Musical/Modo Música (seções 12/21 do ECHO_SPEC).

🔥 Por pessoa (2026-08-26) - todo feedback é do `discord_user_id` de quem deu
o 👍/👎, nunca do dono - Modo Música é social.

Duas forças BEM diferentes (pedido do usuário: "Diferenciar feedback
explícito de feedback passivo. 👍/👎 representam sinais fortes e permanentes.
Pular cedo, ouvir até o final... são sinais fracos e acumulativos"):
- **Forte** (👍/👎 explícito): ajuste maior, aplicado na hora.
- **Fraco** (passivo, tempo de escuta): um evento isolado NÃO ajusta peso -
  só depois de um padrão consistente (`historico.contar_eventos_fracos_
  recentes`) é que vira um ajuste pequeno de verdade."""
from echo.core import artistas as artistas_mod
from echo.core import perfil as perfil_mod
from echo.core import historico as historico_mod
from echo.core import pool as pool_mod
from echo.providers import ProvedorIndisponivel, obter_provedor

AJUSTE_POSITIVO = 0.08
AJUSTE_NEGATIVO = -0.12

AJUSTE_PASSIVO_POSITIVO = 0.03
AJUSTE_PASSIVO_NEGATIVO = -0.03
MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR = 3


def processar_feedback(discord_user_id, track_id, feedback, genero=None):
    """`genero` vem de quem está mandando o feedback (a GAIA reenvia o gênero
    dominante que recebeu junto com a faixa no Radar) - sem ele, o feedback ainda fica
    registrado no histórico, só não ajusta peso (não dá pra ajustar um gênero que não
    se sabe qual é).

    Todo voto (positivo OU negativo) tira a faixa exata do pool
    (`pool.remover_track`, 2026-08-26) - só quem NUNCA foi avaliado
    continua lá ("Musicas sem voto não saem do pool"). 🔥 Só a faixa exata,
    nunca o artista inteiro (2026-08-27, pedido do usuário: "um 👎 em 1
    musica n pode condenar todas desse artista")."""
    # Garante as notas iniciais (reconstruídas do histórico) ANTES de gravar
    # este voto - senão a reconstrução já o incluiria e ele contaria 2x.
    artistas_mod.carregar(discord_user_id)
    entrada = historico_mod.registrar_feedback(discord_user_id, track_id, feedback)
    if entrada is None:
        return None

    if genero:
        perfil = perfil_mod.carregar_perfil(discord_user_id)
        delta = AJUSTE_POSITIVO if feedback == "positivo" else AJUSTE_NEGATIVO
        perfil_mod.ajustar_peso_genero(perfil, genero, delta)
        perfil_mod.salvar_perfil(discord_user_id, perfil)

    pool_mod.remover_track(discord_user_id, entrada["titulo"], entrada["artista"])
    try:
        provedor = obter_provedor()
    except Exception:
        provedor = None
    artistas_mod.registrar_voto(discord_user_id, entrada["titulo"], entrada["artista"], feedback, provedor)

    return entrada


def processar_feedback_ao_vivo(discord_user_id, provedor, titulo, artista, feedback, abrir_prova=True):
    """👍/👎 nos botões do Modo Música do ERIS (2026-08-26, pedido do usuário:
    "quando ela toca uma musica, podia aparecer botoes de like, dislike e
    next") - diferente do Radar, a faixa tocada ao vivo pode nunca ter
    passado por `historico.registrar_recomendacao` (veio de uma busca livre
    do usuário ou do pool, não de uma edição fechada do Radar) - cria a
    entrada no histórico na hora se ela não existir, em vez de devolver
    None. O gênero não vem de quem chama (o ERIS não sabe gênero, só
    artista/título) - resolvido aqui mesmo via provedor.

    Todo voto tira a faixa exata do pool (`pool.remover_track`,
    2026-08-26 - "Musicas sem voto não saem do pool"). 🔥 Só a faixa exata,
    nunca o artista inteiro (2026-08-27, pedido do usuário: "um 👎 em 1
    musica n pode condenar todas desse artista. Assim como o like n aprova
    todas tbm, algumas eu gosto e outras nao").

    O voto também atualiza a nota do artista (`artistas.py`, 2026-09-26);
    `abrir_prova=False` (importação de votos antigos) só mexe na nota, sem
    disparar a regra das 5 chances.

    Trocar de voto (2026-10-12, pedido do usuário: "o siren tem de permitir
    ficar trocando o like e dislike") desfaz o voto anterior antes de
    aplicar o novo, e repetir o mesmo voto não conta 2x."""
    track_id = historico_mod.track_id(titulo, artista)
    artistas_mod.carregar(discord_user_id)  # ver processar_feedback: evita contar este voto 2x
    anterior = historico_mod.obter_voto(discord_user_id, titulo, artista)
    if anterior == feedback:
        return historico_mod.registrar_feedback(discord_user_id, track_id, feedback)
    generos = _generos_do_artista(provedor, artista)
    if anterior:
        _desfazer_voto(discord_user_id, generos, titulo, artista, anterior)

    entrada = historico_mod.registrar_feedback(discord_user_id, track_id, feedback)
    if entrada is None:
        historico_mod.registrar_recomendacao(discord_user_id, titulo, artista, reason="modo_musica", category=None)
        entrada = historico_mod.registrar_feedback(discord_user_id, track_id, feedback)

    if generos:
        _ajustar_genero(discord_user_id, generos[0], AJUSTE_POSITIVO if feedback == "positivo" else AJUSTE_NEGATIVO)

    pool_mod.remover_track(discord_user_id, titulo, artista)
    artistas_mod.registrar_voto(discord_user_id, titulo, artista, feedback, provedor, abrir_prova=abrir_prova)

    return entrada


def remover_voto_ao_vivo(discord_user_id, provedor, titulo, artista):
    """Clicar de novo no 👍/👎 já marcado (SIREN, 2026-10-12): a faixa volta a
    não ter voto. Desfaz o ajuste de gênero e a nota do artista do voto que
    existia. Devolve o voto removido (ou None se não havia)."""
    artistas_mod.carregar(discord_user_id)
    anterior = historico_mod.obter_voto(discord_user_id, titulo, artista)
    if anterior:
        _desfazer_voto(discord_user_id, _generos_do_artista(provedor, artista), titulo, artista, anterior)
    return anterior


def _generos_do_artista(provedor, artista):
    if provedor is None:
        return []
    try:
        return provedor.resolver_generos([artista]).get(artista.strip().lower(), [])
    except ProvedorIndisponivel:
        return []


def _ajustar_genero(discord_user_id, genero, delta):
    perfil = perfil_mod.carregar_perfil(discord_user_id)
    perfil_mod.ajustar_peso_genero(perfil, genero, delta)
    perfil_mod.salvar_perfil(discord_user_id, perfil)


def _desfazer_voto(discord_user_id, generos, titulo, artista, voto):
    historico_mod.limpar_feedback(discord_user_id, historico_mod.track_id(titulo, artista))
    if generos:
        _ajustar_genero(discord_user_id, generos[0], -(AJUSTE_POSITIVO if voto == "positivo" else AJUSTE_NEGATIVO))
    artistas_mod.desfazer_voto(discord_user_id, artista, voto)


def processar_feedback_passivo(discord_user_id, provedor, titulo, artista, fracao_tocada, pulado, momento_do_skip=None):
    """Sinal FRACO (2026-08-26) - sempre registra o evento bruto
    (`historico.registrar_evento_escuta`), mas só ajusta peso de gênero
    depois de `MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR` sinais consistentes na
    mesma direção pro mesmo artista (um skip isolado não significa rejeição
    - pode ser só "não tava a fim dessa agora"). Fração no meio-termo
    (nem claramente pulada cedo, nem claramente ouvida quase inteira) não
    conta como sinal em nenhuma direção."""
    historico_mod.registrar_evento_escuta(discord_user_id, titulo, artista, fracao_tocada, pulado, momento_do_skip)

    negativo = pulado and fracao_tocada is not None and fracao_tocada < 0.25
    positivo = (not pulado) or (fracao_tocada is not None and fracao_tocada > 0.75)
    if not negativo and not positivo:
        return {"ajustou_peso": False}

    contagem = historico_mod.contar_eventos_fracos_recentes(discord_user_id, artista, negativo=negativo)
    if contagem < MINIMO_EVENTOS_FRACOS_PARA_AJUSTAR:
        return {"ajustou_peso": False}

    # 🔥 Padrão consistente confirmado - resolve gênero e aplica um ajuste
    # PEQUENO (bem menor que o feedback explícito, ver AJUSTE_PASSIVO_*).
    try:
        generos = provedor.resolver_generos([artista]).get(artista.strip().lower(), [])
    except ProvedorIndisponivel:
        generos = []
    if not generos:
        return {"ajustou_peso": False}

    perfil = perfil_mod.carregar_perfil(discord_user_id)
    delta = AJUSTE_PASSIVO_NEGATIVO if negativo else AJUSTE_PASSIVO_POSITIVO
    perfil_mod.ajustar_peso_genero(perfil, generos[0], delta)
    perfil_mod.salvar_perfil(discord_user_id, perfil)
    return {"ajustou_peso": True, "negativo": negativo}

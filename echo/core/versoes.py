# -*- coding: utf-8 -*-
"""Versões derivadas (nightcore, AMV, sped up...) trocadas pela oficial
(2026-10-17, pedido do usuário: "tem como fazer o siren recomendar as musicas
oficiais em vez desses nightcore e amv? [...] A black betty msm eu curto, mas
tem de ser a certa").

No Last.fm, o canal do YouTube que subiu o nightcore/AMV vira o "artista"
("BLEACH AMV", "PluggedToNightcore"). Cada canal conta como um artista
diferente, então descurtir um não mudava nada nos outros, e a regra das 5
chances (`artistas.py`) ainda trazia mais 5 faixas do canal descurtido.

Regra: faixa derivada nunca entra no Caos como está. Quem tem provedor tenta
achar a oficial pelo título (`track.search`); sem achar, a faixa sai."""
import re

from echo.core import historico as historico_mod
from echo.providers import ProvedorIndisponivel

# No nome do canal, "amv"/"nightcore" aparecem colados ("VermillionAMV",
# "PluggedToNightcore"), então ali vale como trecho. No título, só palavra
# inteira, pra não pegar música de verdade por acidente.
_PADRAO_CANAL = re.compile(r"nightcore|nightstep|daycore|amvs?\b|amv|anime ?mv", re.IGNORECASE)
_PADRAO_TITULO = re.compile(
    r"\b(?:nightcore|nightstep|nightstyle|daycore|amvs?|gmv|anime ?mv|mep|sped ?up|speed ?up|slowed|8d audio)\b",
    re.IGNORECASE,
)

# Ruído típico desses títulos: "「Nightcore」→ X", "√Bestamvsofalltime ▪ X",
# "X - Anime MV ♫", "[Nightcore] X", "X ▹Lyrics◃".
_ENTRE_DELIMITADORES = re.compile(r"[\(\[「【╭▹](.*?)[\)\]」】╯◃]")
_PALAVRAS_RUIDO = re.compile(
    r"\b(?:nightcore|nightstep|nightstyle|daycore|amvs?|gmv|anime ?mv|mep|sped ?up|speed ?up|slowed|"
    r"8d audio|w/ ?lyrics|lyrics?|remix|hd|hq|720p|1080p|bestamvsofalltime)\b",
    re.IGNORECASE,
)

# Abaixo disso o resultado da busca costuma ser outro upload de canal, não a
# música (ex.: "Naruto - Itachi VS. Sasuke", 110 ouvintes).
MINIMO_OUVINTES_OFICIAL = 1000


def eh_derivada(artista, titulo=""):
    return bool(_PADRAO_CANAL.search(artista or "") or _PADRAO_TITULO.search(titulo or ""))


def titulo_limpo(titulo, artista=""):
    """Só o nome da música: sem marcação de nightcore/AMV, colchetes, nome
    do canal e símbolos."""
    texto = _ENTRE_DELIMITADORES.sub(" ", titulo or "")
    texto = _PALAVRAS_RUIDO.sub(" ", texto)
    if artista.strip():
        texto = re.sub(rf"\b{re.escape(artista.strip())}\b", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"[^\w'&!?.,*+ -]+", " ", texto)
    texto = re.sub(r"(?:^|\s)[-.,]+(?=\s|$)", " ", texto)
    return re.sub(r"\s+", " ", texto).strip(" -")


def _pistas_de_artista(titulo):
    """Texto entre colchetes/parênteses que sobra sem o ruído: nos uploads
    de nightcore costuma ser o artista original ("Hero [Pegboard Nerds]")."""
    pistas = []
    for trecho in _ENTRE_DELIMITADORES.findall(titulo or ""):
        trecho = re.sub(r"\s+", " ", _PALAVRAS_RUIDO.sub(" ", trecho)).strip(" -/")
        if len(trecho) >= 2 and trecho.lower() not in {p.lower() for p in pistas}:
            pistas.append(trecho)
    return pistas


def _normalizar(texto):
    return re.sub(r"[^\w]+", " ", (texto or "").lower()).strip()


def _corresponde(resultado, consulta):
    """Mesmo título, ou o título dentro da consulta junto com o nome do
    artista ("Move - Thousand foot krutch" -> Thousand Foot Krutch, "Move")."""
    titulo = _normalizar(resultado["titulo"])
    artista = _normalizar(resultado["artista"])
    consulta = f" {_normalizar(consulta)} "
    if not titulo:
        return False
    if consulta.strip() == titulo:
        return True
    return f" {titulo} " in consulta and f" {artista} " in consulta


def _ouvintes(resultado):
    try:
        return int(resultado.get("ouvintes") or 0)
    except (TypeError, ValueError):
        return 0


def _melhor_resultado(provedor, consulta):
    try:
        resultados = provedor.buscar_faixa(consulta, resolver_generos=False)
    except ProvedorIndisponivel:
        return None
    except Exception:
        return None
    for resultado in resultados:
        if eh_derivada(resultado["artista"], resultado["titulo"]):
            continue
        if _ouvintes(resultado) >= MINIMO_OUVINTES_OFICIAL and _corresponde(resultado, consulta):
            return resultado
    return None


def buscar_oficial(provedor, artista, titulo):
    """Primeiro resultado do provedor que não seja derivado, com o mesmo
    título e ouvintes suficientes. Tenta antes com cada pista de artista do
    título, porque título curto sozinho ("Hero") cai no artista mais ouvido
    com esse nome. `None` se não achar."""
    consulta = titulo_limpo(titulo, artista)
    if len(consulta) < 2:
        return None
    resultado = None
    for pista in _pistas_de_artista(titulo):
        resultado = _melhor_resultado(provedor, f"{consulta} {pista}")
        if resultado:
            break
    resultado = resultado or _melhor_resultado(provedor, consulta)
    if not resultado:
        return None
    try:
        generos = provedor.resolver_generos([resultado["artista"]]).get(resultado["artista"].strip().lower(), [])
    except Exception:
        generos = []
    return {**resultado, "generos": generos}


def oficializar(provedor, candidatos, discord_user_id=None):
    """Troca cada candidato derivado pela versão oficial e descarta os que
    não têm uma. Os demais campos do candidato (fonte, score...) ficam.
    Com `discord_user_id`, a oficial já votada também sai, como qualquer
    faixa votada."""
    votadas = historico_mod.chaves_frouxas_votadas(discord_user_id) if discord_user_id else set()
    resultado = []
    cache = {}
    for candidato in candidatos:
        if not eh_derivada(candidato["artista"], candidato["titulo"]):
            resultado.append(candidato)
            continue
        chave = (candidato["artista"].lower(), candidato["titulo"].lower())
        if chave not in cache:
            cache[chave] = buscar_oficial(provedor, candidato["artista"], candidato["titulo"])
        oficial = cache[chave]
        if not oficial:
            print(f" [ECHO] Versão derivada descartada (sem oficial): {candidato['artista']} - {candidato['titulo']}")
            continue
        if historico_mod.chave_frouxa(oficial["titulo"], oficial["artista"]) in votadas:
            continue
        print(f" [ECHO] Versão derivada trocada: {candidato['artista']} - {candidato['titulo']} -> {oficial['artista']} - {oficial['titulo']}")
        resultado.append({
            **candidato,
            "titulo": oficial["titulo"],
            "artista": oficial["artista"],
            "generos": oficial.get("generos") or candidato.get("generos", []),
            "popularidade": oficial.get("popularidade", candidato.get("popularidade")),
            "url_lastfm": oficial.get("url_lastfm"),
        })
    return resultado

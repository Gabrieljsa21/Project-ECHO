# -*- coding: utf-8 -*-
"""Implementação de referência do provedor musical (seção 17 do ECHO_SPEC) usando a
API do Last.fm - escolhida em vez do Spotify (2026-08-25, ver `ARQUITETURA.md`)
porque não exige assinatura paga nem login de usuário pra dado público (chave de
API grátis em last.fm/api/account/create), e porque a Spotify removeu justamente o
endpoint de "novos lançamentos" (`GET /browse/new-releases`) numa mudança de
política de fevereiro/março de 2026, sem substituto oficial.

Sem streaming/playback: Last.fm é um serviço de metadado/scrobbling, não toca
música nem gerencia playlist - os métodos de playback/playlist (Fase 3 do
ECHO_SPEC) sempre levantam `ProvedorIndisponivel` aqui; quando essa fase chegar,
precisa de OUTRO provedor (Spotify com OAuth de usuário de verdade, ou outro
serviço de streaming) - mesmo princípio de "núcleo do Modo DJ sobrevive à troca de
integração" (seção 31.7)."""
import os
import math
import time
import requests

from echo.providers import ProvedorMusical, ProvedorIndisponivel

_URL_BASE = "http://ws.audioscrobbler.com/2.0/"

# 🔥 Cache em nível de MÓDULO, não de instância (2026-09-06, achado do
# usuário no Project-SIREN: "porque está demorando pra entrar na página
# Descoberta... entrando, saindo e entrando de novo também demora") -
# `obter_provedor()` (`providers/__init__.py`) cria uma instância NOVA a
# cada chamada, então um cache em `self` seria descartado antes de servir
# pra nada. Sem isso, `/em_alta` fazia 1 chamada de chart + até
# `_MAX_ARTISTAS_PARA_RESOLVER_GENERO` chamadas (1 POR artista, Last.fm não
# tem endpoint de gênero em lote) - TODA VEZ, mesmo pedindo a mesma coisa
# 10 segundos depois.
_TTL_LANCAMENTOS_SEGUNDOS = 600  # 10min - chart global não muda a cada request
_TTL_GENERO_SEGUNDOS = 7 * 24 * 3600  # 7 dias - gênero de artista é essencialmente estático
_cache_lancamentos = {}  # limite -> (resultado, timestamp)
_cache_generos = {}  # nome_artista_lower -> (generos, timestamp)

# 🔥 Last.fm não tem campo de popularidade normalizado (0-100) como o Spotify tinha
# - só `listeners` (contagem bruta, sem teto). Escala LOGARÍTMICA entre um piso
# (dado pouco confiável abaixo disso, vira sinal ausente) e um teto (faixa global
# muito popular) - aproximação documentada, não um score oficial da plataforma.
_LISTENERS_PISO = 50
_LISTENERS_TETO = 2_000_000
# 🔥 50 (2026-08-25, achado real testando com playlists de verdade) - o cadastro
# em lote (`/perfil/importar_artistas`) é uma ação RARA e disparada pelo próprio
# usuário (colar uma playlist inteira), não um hot path repetido - um teto baixo
# demais (20) truncava silenciosamente o gênero de metade de uma importação real
# de 3 playlists (38 artistas únicos) sem avisar ninguém. 50 ainda protege contra
# uma explosão de verdade (ex.: um candidato de Radar com centenas de faixas).
_MAX_ARTISTAS_PARA_RESOLVER_GENERO = 50


def _normalizar_popularidade(listeners):
    try:
        listeners = int(listeners)
    except (TypeError, ValueError):
        return None
    if listeners < _LISTENERS_PISO:
        return None
    log_piso = math.log10(_LISTENERS_PISO)
    log_teto = math.log10(_LISTENERS_TETO)
    log_atual = math.log10(min(listeners, _LISTENERS_TETO))
    return round(max(0.0, min(100.0, (log_atual - log_piso) / (log_teto - log_piso) * 100)))


class ProvedorLastfm(ProvedorMusical):
    def __init__(self):
        self.api_key = os.getenv("LASTFM_API_KEY")
        # 🔥 Username vinculado (2026-08-25, Fase 2 antecipada) - se o usuário já
        # usa scrobbling (Spotify -> Last.fm, ver last.fm/about/trackmymusic), o
        # histórico REAL de escuta fica disponível sem precisar de OAuth nenhum
        # do Spotify, só desse username público. Sem ele, os métodos abaixo
        # continuam indisponíveis (não é obrigatório pro resto do provedor).
        self.username = os.getenv("LASTFM_USERNAME")

    def esta_configurado(self):
        return bool(self.api_key)

    def tem_username_vinculado(self):
        return bool(self.username)

    def _get(self, method, **params):
        if not self.esta_configurado():
            raise ProvedorIndisponivel("LASTFM_API_KEY não configurada no .env")
        try:
            resp = requests.get(_URL_BASE, params={
                "method": method, "api_key": self.api_key, "format": "json", **params,
            }, timeout=10)
            resp.raise_for_status()
            dados = resp.json()
        except ProvedorIndisponivel:
            raise
        except Exception as e:
            raise ProvedorIndisponivel(f"falha na chamada ao Last.fm: {e}")
        if "error" in dados:
            raise ProvedorIndisponivel(f"Last.fm respondeu erro: {dados.get('message', dados['error'])}")
        return dados

    def _resolver_generos_por_artista(self, nomes_artistas):
        """1 chamada POR artista (Last.fm não tem endpoint de gênero em lote) -
        capado em `_MAX_ARTISTAS_PARA_RESOLVER_GENERO` pra não explodir o número
        de requisições numa lista grande de candidatos. Cacheado por artista
        (`_cache_generos`, TTL de dias) - gênero praticamente nunca muda, então
        um artista já resolvido antes (em QUALQUER chamada, radar/em_alta/
        importação) nunca precisa de rede de novo tão cedo."""
        nomes_unicos = list(dict.fromkeys(n for n in nomes_artistas if n))[:_MAX_ARTISTAS_PARA_RESOLVER_GENERO]
        agora = time.time()
        generos = {}
        for nome in nomes_unicos:
            chave = nome.lower()
            em_cache = _cache_generos.get(chave)
            if em_cache is not None and (agora - em_cache[1]) < _TTL_GENERO_SEGUNDOS:
                generos[chave] = em_cache[0]
                continue
            try:
                dados = self._get("artist.gettoptags", artist=nome, autocorrect=1)
                tags = dados.get("toptags", {}).get("tag", [])
                lista_generos = [t["name"].lower() for t in tags[:5]]
            except ProvedorIndisponivel:
                lista_generos = []
            generos[chave] = lista_generos
            _cache_generos[chave] = (lista_generos, agora)
        return generos

    def _normalizar_faixa(self, faixa, generos_por_artista, fonte):
        artista_bruto = faixa.get("artist")
        nome_artista = artista_bruto.get("name") if isinstance(artista_bruto, dict) else (artista_bruto or "Desconhecido")
        return {
            "titulo": faixa.get("name", "?"),
            "artista": nome_artista,
            "album": None,  # Last.fm não expõe álbum nesses endpoints sem 1 chamada extra por faixa
            "data_lancamento": None,  # Last.fm não tem data de lançamento (é scrobbling, não catálogo)
            "popularidade": _normalizar_popularidade(faixa.get("listeners")),
            "generos": generos_por_artista.get(nome_artista.lower(), []),
            "url_lastfm": faixa.get("url"),
            "fonte": fonte,
        }

    def buscar_faixa(self, query):
        dados = self._get("track.search", track=query, limit=20)
        faixas = dados.get("results", {}).get("trackmatches", {}).get("track", [])
        nomes_artistas = [f.get("artist") for f in faixas if isinstance(f.get("artist"), str)]
        generos = self._resolver_generos_por_artista(nomes_artistas)
        return [self._normalizar_faixa(f, generos, "busca") for f in faixas]

    def obter_faixas_do_artista(self, nome, limite=10):
        """Substitui o hack de `buscar_faixa('artist:"X"')` que a implementação
        anterior (Spotify) precisava - Last.fm tem um endpoint dedicado de
        verdade pras faixas mais tocadas de um artista específico."""
        dados = self._get("artist.gettoptracks", artist=nome, limit=limite, autocorrect=1)
        faixas = dados.get("toptracks", {}).get("track", [])
        generos = self._resolver_generos_por_artista([nome])
        return [self._normalizar_faixa(f, generos, "artista_favorito") for f in faixas]

    def obter_faixas_por_tag(self, tag, limite=10):
        """Candidatos por GÊNERO (seção 6.3/6.4 - descoberta/exploração) - o
        gênero já é conhecido de antemão (é o próprio tag pedido), não precisa
        de chamada extra de `artist.gettoptags`.

        🔥 Achado real (2026-08-26, investigando "/caos parou de tocar depois
        de 1 música") - `tag.gettoptracks` devolve a lista dentro de
        `{"tracks": {"track": [...]}}`, NÃO `{"toptracks": {...}}` como
        `artist.gettoptracks` (cada endpoint do Last.fm usa uma chave de
        wrapper diferente, apesar do nome do método parecer igual) - com a
        chave errada, isso SEMPRE devolveu lista vazia, silenciosamente,
        desde que foi escrito - toda sugestão "por gênero" (descoberta/
        exploração) do Radar E da continuação ao vivo nunca teve candidato
        nenhum vindo daqui, só de artista favorito/chart global."""
        dados = self._get("tag.gettoptracks", tag=tag, limit=limite)
        faixas = dados.get("tracks", {}).get("track", [])
        resultado = []
        for f in faixas:
            candidato = self._normalizar_faixa(f, {}, "tag")
            candidato["generos"] = [tag.lower()]
            resultado.append(candidato)
        return resultado

    def obter_lancamentos_novos(self, limite=20):
        """Last.fm não tem conceito de "lançamento" (não guarda data de release,
        é scrobbling de reprodução) - usa o chart GLOBAL de mais tocadas como
        fonte de "relevância atual" (seção 6.2 do ECHO_SPEC: "músicas realmente
        populares, culturalmente relevantes"). Documentado como aproximação, não
        um feed de novidades de verdade - mesma ressalva que já existia na
        implementação Spotify anterior (sem popularidade por faixa).

        Cacheado por `limite` (`_cache_lancamentos`, TTL de minutos) - chart
        global não muda segundo a segundo, e sem isso TODA chamada refazia a
        resolução de gênero de até 50 artistas do zero (achado do usuário,
        ver comentário em `_cache_generos` acima)."""
        agora = time.time()
        em_cache = _cache_lancamentos.get(limite)
        if em_cache is not None and (agora - em_cache[1]) < _TTL_LANCAMENTOS_SEGUNDOS:
            return em_cache[0]
        dados = self._get("chart.gettoptracks", limit=min(limite, 50))
        faixas = dados.get("tracks", {}).get("track", [])
        nomes_artistas = [f.get("artist", {}).get("name") for f in faixas if isinstance(f.get("artist"), dict)]
        generos = self._resolver_generos_por_artista(nomes_artistas)
        resultado = [self._normalizar_faixa(f, generos, "em_alta") for f in faixas]
        _cache_lancamentos[limite] = (resultado, agora)
        return resultado

    def obter_faixas_em_alta(self, limite=20):
        raise ProvedorIndisponivel(
            "Last.fm não distingue 'em alta' de 'popular globalmente' - use "
            "obter_lancamentos_novos (mesma fonte, chart.gettoptracks)"
        )

    def _exigir_username(self):
        if not self.tem_username_vinculado():
            raise ProvedorIndisponivel(
                "LASTFM_USERNAME não configurado no .env - vincule seu username "
                "do Last.fm (last.fm/user/<usuario>) pra usar histórico real de escuta"
            )

    def obter_reproduzidas_recentemente(self, limite=20):
        """`user.getrecenttracks` - histórico real de reprodução (via scrobbling,
        ex.: Spotify -> Last.fm). Formato de artista É DIFERENTE dos outros
        endpoints (`artist.#text`, não `artist.name`) - a própria API do Last.fm
        não é consistente entre métodos aqui."""
        self._exigir_username()
        dados = self._get("user.getrecenttracks", user=self.username, limit=limite)
        faixas = dados.get("recenttracks", {}).get("track", [])
        resultado = []
        for f in faixas:
            artista_bruto = f.get("artist")
            nome_artista = artista_bruto.get("#text") if isinstance(artista_bruto, dict) else (artista_bruto or "Desconhecido")
            resultado.append({
                "titulo": f.get("name", "?"),
                "artista": nome_artista,
                "album": None,
                "data_lancamento": None,
                "popularidade": None,
                "generos": [],
                "url_lastfm": f.get("url"),
                "fonte": "recente_usuario",
            })
        return resultado

    def obter_top_faixas_usuario(self, limite=20, periodo="12month"):
        """`user.gettoptracks` - faixas mais tocadas de verdade pelo usuário
        (`periodo`: overall/7day/1month/3month/6month/12month - 12 meses por
        padrão, equilíbrio entre "gosto atual" e "gosto de sempre")."""
        self._exigir_username()
        dados = self._get("user.gettoptracks", user=self.username, period=periodo, limit=limite)
        faixas = dados.get("toptracks", {}).get("track", [])
        nomes_artistas = [f.get("artist", {}).get("name") for f in faixas if isinstance(f.get("artist"), dict)]
        generos = self._resolver_generos_por_artista(nomes_artistas)
        return [self._normalizar_faixa(f, generos, "historico_usuario") for f in faixas]

    def obter_top_artistas_usuario(self, limite=20, periodo="12month"):
        """`user.gettopartists` - base real pra `core.perfil.
        importar_favoritos_do_historico` (seed do perfil musical a partir do
        histórico de escuta de verdade, em vez de cadastro manual um por um)."""
        self._exigir_username()
        dados = self._get("user.gettopartists", user=self.username, period=periodo, limit=limite)
        artistas = dados.get("topartists", {}).get("artist", [])
        generos = self._resolver_generos_por_artista([a.get("name") for a in artistas])
        return [
            {
                "nome": a["name"],
                "playcount": int(a.get("playcount", 0)),
                "rank": int(a.get("rank", i + 1)),
                "generos": generos.get(a["name"].lower(), []),
            }
            for i, a in enumerate(artistas)
        ]

    def criar_playlist(self, nome, descricao=""):
        raise ProvedorIndisponivel("Last.fm não tem playlists/streaming - Fase 3 precisa de outro provedor (ex.: Spotify com OAuth de usuário)")

    def adicionar_faixa_playlist(self, playlist_id, track_id):
        raise ProvedorIndisponivel("Last.fm não tem playlists/streaming - Fase 3 precisa de outro provedor (ex.: Spotify com OAuth de usuário)")

    def tocar_faixa(self, track_id):
        raise ProvedorIndisponivel("Last.fm não toca música - Fase 3 precisa de outro provedor (ex.: Spotify com OAuth de usuário)")

    def resolver_generos(self, nomes_artistas):
        return self._resolver_generos_por_artista(nomes_artistas)

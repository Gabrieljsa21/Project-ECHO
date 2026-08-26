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
import requests

from echo.providers import ProvedorMusical, ProvedorIndisponivel

_URL_BASE = "http://ws.audioscrobbler.com/2.0/"

# 🔥 Last.fm não tem campo de popularidade normalizado (0-100) como o Spotify tinha
# - só `listeners` (contagem bruta, sem teto). Escala LOGARÍTMICA entre um piso
# (dado pouco confiável abaixo disso, vira sinal ausente) e um teto (faixa global
# muito popular) - aproximação documentada, não um score oficial da plataforma.
_LISTENERS_PISO = 50
_LISTENERS_TETO = 2_000_000
_MAX_ARTISTAS_PARA_RESOLVER_GENERO = 20


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

    def esta_configurado(self):
        return bool(self.api_key)

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
        de requisições numa lista grande de candidatos."""
        nomes_unicos = list(dict.fromkeys(n for n in nomes_artistas if n))[:_MAX_ARTISTAS_PARA_RESOLVER_GENERO]
        generos = {}
        for nome in nomes_unicos:
            try:
                dados = self._get("artist.gettoptags", artist=nome, autocorrect=1)
                tags = dados.get("toptags", {}).get("tag", [])
                generos[nome.lower()] = [t["name"].lower() for t in tags[:5]]
            except ProvedorIndisponivel:
                generos[nome.lower()] = []
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
        de chamada extra de `artist.gettoptags`."""
        dados = self._get("tag.gettoptracks", tag=tag, limit=limite)
        faixas = dados.get("toptracks", {}).get("track", [])
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
        implementação Spotify anterior (sem popularidade por faixa)."""
        dados = self._get("chart.gettoptracks", limit=min(limite, 50))
        faixas = dados.get("tracks", {}).get("track", [])
        nomes_artistas = [f.get("artist", {}).get("name") for f in faixas if isinstance(f.get("artist"), dict)]
        generos = self._resolver_generos_por_artista(nomes_artistas)
        return [self._normalizar_faixa(f, generos, "em_alta") for f in faixas]

    def obter_faixas_em_alta(self, limite=20):
        raise ProvedorIndisponivel(
            "Last.fm não distingue 'em alta' de 'popular globalmente' - use "
            "obter_lancamentos_novos (mesma fonte, chart.gettoptracks)"
        )

    def obter_reproduzidas_recentemente(self, limite=20):
        raise ProvedorIndisponivel("requer username do Last.fm vinculado (Fase 2 do ECHO_SPEC) - não implementado ainda")

    def obter_top_faixas_usuario(self, limite=20):
        raise ProvedorIndisponivel("requer username do Last.fm vinculado (Fase 2 do ECHO_SPEC) - não implementado ainda")

    def obter_top_artistas_usuario(self, limite=20):
        raise ProvedorIndisponivel("requer username do Last.fm vinculado (Fase 2 do ECHO_SPEC) - não implementado ainda")

    def criar_playlist(self, nome, descricao=""):
        raise ProvedorIndisponivel("Last.fm não tem playlists/streaming - Fase 3 precisa de outro provedor (ex.: Spotify com OAuth de usuário)")

    def adicionar_faixa_playlist(self, playlist_id, track_id):
        raise ProvedorIndisponivel("Last.fm não tem playlists/streaming - Fase 3 precisa de outro provedor (ex.: Spotify com OAuth de usuário)")

    def tocar_faixa(self, track_id):
        raise ProvedorIndisponivel("Last.fm não toca música - Fase 3 precisa de outro provedor (ex.: Spotify com OAuth de usuário)")

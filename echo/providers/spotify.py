# -*- coding: utf-8 -*-
"""Implementação de referência do provedor musical (seção 17 do ECHO_SPEC) usando a
Web API do Spotify, fluxo Client Credentials (sem login de usuário - só dados
públicos: busca, lançamentos, gênero de artista). Os métodos que exigem autorização
de USUÁRIO (histórico de reprodução, top faixas/artistas, playlists) pertencem à Fase
2/3 do ECHO_SPEC (comportamento real, playlists) - aqui eles levantam
`ProvedorIndisponivel` com uma mensagem clara em vez de fingir suporte."""
import os
import time
import base64
import requests

from echo.providers import ProvedorMusical, ProvedorIndisponivel

_URL_TOKEN = "https://accounts.spotify.com/api/token"
_URL_BASE = "https://api.spotify.com/v1"

# 🔥 cache de módulo (não por instância) - o token client-credentials é o mesmo pra
# qualquer requisição do processo, recriar uma instância de ProvedorSpotify a cada
# request HTTP (api_bridge.py) não deveria forçar reautenticação.
_token_cache = {"valor": None, "expira_em": 0}


class ProvedorSpotify(ProvedorMusical):
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    def esta_configurado(self):
        return bool(self.client_id and self.client_secret)

    def _obter_token(self):
        if not self.esta_configurado():
            raise ProvedorIndisponivel("SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET não configurados no .env")
        if _token_cache["valor"] and time.time() < _token_cache["expira_em"]:
            return _token_cache["valor"]
        credenciais = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            resp = requests.post(
                _URL_TOKEN,
                data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {credenciais}"},
                timeout=10,
            )
            resp.raise_for_status()
            dados = resp.json()
        except Exception as e:
            raise ProvedorIndisponivel(f"falha ao autenticar no Spotify: {e}")
        _token_cache["valor"] = dados["access_token"]
        _token_cache["expira_em"] = time.time() + dados.get("expires_in", 3600) - 30
        return _token_cache["valor"]

    def _get(self, caminho, params=None):
        token = self._obter_token()
        try:
            resp = requests.get(
                f"{_URL_BASE}{caminho}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
                timeout=10,
            )
            if resp.status_code == 429:
                raise ProvedorIndisponivel("rate limit do Spotify atingido")
            resp.raise_for_status()
            return resp.json()
        except ProvedorIndisponivel:
            raise
        except Exception as e:
            raise ProvedorIndisponivel(f"falha na chamada ao Spotify: {e}")

    def _generos_por_artista(self, ids_artistas):
        """1 chamada em lote a cada 50 ids - a Spotify só expõe gênero no nível de
        ARTISTA, nunca de álbum/faixa diretamente."""
        ids_unicos = list(dict.fromkeys(i for i in ids_artistas if i))
        generos = {}
        for i in range(0, len(ids_unicos), 50):
            lote = ids_unicos[i:i + 50]
            dados = self._get("/artists", {"ids": ",".join(lote)})
            for artista in dados.get("artists", []):
                if artista:
                    generos[artista["id"]] = artista.get("genres", [])
        return generos

    def _normalizar_faixa(self, faixa, generos):
        artista = faixa["artists"][0] if faixa.get("artists") else {"id": None, "name": "Desconhecido"}
        return {
            "titulo": faixa["name"],
            "artista": artista["name"],
            "album": faixa.get("album", {}).get("name"),
            "data_lancamento": faixa.get("album", {}).get("release_date"),
            "popularidade": faixa.get("popularity"),
            "generos": generos.get(artista["id"], []),
            "url_spotify": faixa.get("external_urls", {}).get("spotify"),
            "fonte": "busca",
        }

    def buscar_faixa(self, query):
        dados = self._get("/search", {"q": query, "type": "track", "limit": 20})
        faixas = dados.get("tracks", {}).get("items", [])
        ids_artistas = [f["artists"][0]["id"] for f in faixas if f.get("artists")]
        generos = self._generos_por_artista(ids_artistas)
        return [self._normalizar_faixa(f, generos) for f in faixas]

    def obter_lancamentos_novos(self, limite=20):
        dados = self._get("/browse/new-releases", {"limit": min(limite, 50)})
        albuns = dados.get("albums", {}).get("items", [])
        ids_artistas = [a["artists"][0]["id"] for a in albuns if a.get("artists")]
        generos = self._generos_por_artista(ids_artistas)
        # 🔥 o endpoint de lançamentos devolve ÁLBUM, não faixa - sem popularidade por
        # faixa individual sem 1 chamada extra por álbum (custo alto demais numa
        # varredura de até 50 lançamentos). Popularidade fica None (sinal ausente),
        # o ranking (`core/recomendador.py`) trata isso como 0, nunca inventa número.
        return [
            {
                "titulo": album["name"],
                "artista": album["artists"][0]["name"] if album.get("artists") else "Desconhecido",
                "album": album["name"],
                "data_lancamento": album.get("release_date"),
                "popularidade": None,
                "generos": generos.get(album["artists"][0]["id"], []) if album.get("artists") else [],
                "url_spotify": album.get("external_urls", {}).get("spotify"),
                "fonte": "lancamento",
            }
            for album in albuns
        ]

    def obter_faixas_em_alta(self, limite=20):
        raise ProvedorIndisponivel(
            "Spotify não expõe um endpoint público de 'em alta' via Client Credentials "
            "(precisa de escopo de usuário) - Fase 2/3 do ECHO_SPEC"
        )

    def obter_reproduzidas_recentemente(self, limite=20):
        raise ProvedorIndisponivel("requer autenticação de usuário (Fase 2 do ECHO_SPEC) - não implementado ainda")

    def obter_top_faixas_usuario(self, limite=20):
        raise ProvedorIndisponivel("requer autenticação de usuário (Fase 2 do ECHO_SPEC) - não implementado ainda")

    def obter_top_artistas_usuario(self, limite=20):
        raise ProvedorIndisponivel("requer autenticação de usuário (Fase 2 do ECHO_SPEC) - não implementado ainda")

    def criar_playlist(self, nome, descricao=""):
        raise ProvedorIndisponivel("requer autenticação de usuário (Fase 3 do ECHO_SPEC) - não implementado ainda")

    def adicionar_faixa_playlist(self, playlist_id, track_id):
        raise ProvedorIndisponivel("requer autenticação de usuário (Fase 3 do ECHO_SPEC) - não implementado ainda")

    def tocar_faixa(self, track_id):
        raise ProvedorIndisponivel("requer autenticação de usuário (Fase 3 do ECHO_SPEC) - não implementado ainda")

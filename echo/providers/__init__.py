# -*- coding: utf-8 -*-
"""Abstração do provedor musical (seção 17 do ECHO_SPEC) - o motor de recomendação
(`core/recomendador.py`, `core/radar.py`) nunca fala com uma API de streaming
diretamente, só com essa interface. Trocar de provedor não deve exigir mudança no
ranking/Radar (princípio 7 da seção 31) - prova real disso: a implementação de
referência trocou de Spotify pra Last.fm em 2026-08-25 (ver `lastfm.py` e
`ARQUITETURA.md`) sem tocar em nenhum módulo de `core/`."""


class ProvedorIndisponivel(Exception):
    """Levantada quando o provedor não está configurado (sem credencial) ou a
    chamada externa falhou - nunca deve virar dado inventado, só ausência de
    candidatos (seção 27: "nunca inventar músicas, artistas, datas ou métricas
    quando o provedor não retornar informação confiável")."""


class ProvedorMusical:
    def esta_configurado(self):
        raise NotImplementedError

    def buscar_faixa(self, query):
        raise NotImplementedError

    def obter_faixas_do_artista(self, nome, limite=10):
        raise NotImplementedError

    def obter_faixas_por_tag(self, tag, limite=10):
        raise NotImplementedError

    def obter_lancamentos_novos(self, limite=20):
        raise NotImplementedError

    def obter_faixas_em_alta(self, limite=20):
        raise NotImplementedError

    def obter_reproduzidas_recentemente(self, limite=20):
        raise NotImplementedError

    def obter_top_faixas_usuario(self, limite=20):
        raise NotImplementedError

    def obter_top_artistas_usuario(self, limite=20):
        raise NotImplementedError

    def criar_playlist(self, nome, descricao=""):
        raise NotImplementedError

    def adicionar_faixa_playlist(self, playlist_id, track_id):
        raise NotImplementedError

    def tocar_faixa(self, track_id):
        raise NotImplementedError

    def resolver_generos(self, nomes_artistas):
        """Devolve `{nome.lower(): [generos]}` pros artistas pedidos - usado pra
        cadastro em lote de artista favorito (`core.perfil.
        adicionar_artista_favorito` chamado por fora, ver `api_bridge.py`
        `/perfil/importar_artistas`) sem a LLM precisar chutar gênero."""
        raise NotImplementedError


def obter_provedor():
    """Único provedor implementado na Fase 1 (Last.fm, sem OAuth de usuário - só
    chave de API grátis). Import tardio pra evitar ciclo (lastfm.py importa
    `ProvedorMusical`/`ProvedorIndisponivel` deste módulo)."""
    from echo.providers.lastfm import ProvedorLastfm
    return ProvedorLastfm()

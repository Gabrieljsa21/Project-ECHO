# -*- coding: utf-8 -*-
"""Abstração do provedor musical (seção 17 do ECHO_SPEC) - o motor de recomendação
(`core/recomendador.py`, `core/radar.py`) nunca fala com uma API de streaming
diretamente, só com essa interface. Trocar de provedor (Spotify -> outro) não deve
exigir mudança no ranking/Radar (princípio 7 da seção 31)."""


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


def obter_provedor():
    """Único provedor implementado na Fase 1 (Spotify, Client Credentials). Import
    tardio pra evitar ciclo (spotify.py importa `ProvedorMusical`/`ProvedorIndisponivel`
    deste módulo)."""
    from echo.providers.spotify import ProvedorSpotify
    return ProvedorSpotify()

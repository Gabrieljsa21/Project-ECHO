# -*- coding: utf-8 -*-
"""Ponte HTTP do ECHO (porta 8774) - mesmo padrão de `hestia/api_bridge.py`
(`BaseHTTPRequestHandler` simples, sem framework). Único consumidor: a GAIA
(`integrations/echo_client.py`) - ela decide QUANDO gerar o Radar (Agendador Diário
ou comando do usuário) e COMO apresentar (persona, explicação, seção 13 do
ECHO_SPEC); aqui só o ranking determinístico e a persistência."""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from echo.core import perfil as perfil_mod
from echo.core import radar as radar_mod
from echo.core import feedback as feedback_mod
from echo.core import historico as historico_mod
from echo.core import continuacao as continuacao_mod
from echo.providers import obter_provedor, ProvedorIndisponivel

LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = 8774


def _ler_corpo_json(handler):
    tamanho = int(handler.headers.get("Content-Length", 0))
    try:
        return json.loads(handler.rfile.read(tamanho)) if tamanho else {}
    except Exception:
        return {}


def _coletar_candidatos(provedor, perfil, limite_geral=40, max_artistas=10, max_generos=5):
    """3 fontes - senão o Radar nunca saberia de música de quem o usuário já
    gosta nem teria candidato dedicado pros gêneros preferidos, só o que o
    provedor considera "popular" globalmente:
    1. chart global (`obter_lancamentos_novos`) - alimenta compatibilidade/relevância;
    2. faixas dos artistas favoritos (`obter_faixas_do_artista`) - compatibilidade forte;
    3. faixas por gênero preferido (`obter_faixas_por_tag`) - descoberta/exploração,
       senão essas 2 categorias ficariam só com o que sobra do chart global.
    Para na primeira falha do provedor dentro de cada loop (ex.: rate limit) e
    segue com o que já tiver coletado, em vez de derrubar o Radar inteiro.

    `max_artistas`/`max_generos` (2026-08-26, achado real: `/caos` demorava
    ~10s pra iniciar) - o Radar semanal (rodando em background) pode pagar
    até 1+10+5=16 chamadas sequenciais ao provedor sem problema, mas
    `/radar/semente` chama isso com o usuário esperando AO VIVO numa call -
    reduzido pra bater com a mesma leveza de `continuacao.sugerir_proxima`
    (no máximo 1 artista/3 gêneros na semeadura normal)."""
    candidatos = list(provedor.obter_lancamentos_novos(limite_geral))
    for artista in perfil["favorite_artists"][:max_artistas]:
        try:
            candidatos.extend(provedor.obter_faixas_do_artista(artista["nome"]))
        except ProvedorIndisponivel:
            break
    generos_ordenados = sorted(perfil["preferred_genres"].items(), key=lambda kv: kv[1], reverse=True)
    for genero, _peso in generos_ordenados[:max_generos]:
        try:
            candidatos.extend(provedor.obter_faixas_por_tag(genero))
        except ProvedorIndisponivel:
            break
    return candidatos


class _API(BaseHTTPRequestHandler):
    def _responder_json(self, dados, status=200):
        corpo = json.dumps(dados).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corpo)

    def _responder_404(self):
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        caminho, _, query = self.path.partition("?")
        params = urllib.parse.parse_qs(query)

        if caminho == "/status":
            provedor = obter_provedor()
            self._responder_json({
                "provedor_configurado": provedor.esta_configurado(),
                "username_vinculado": provedor.tem_username_vinculado() if hasattr(provedor, "tem_username_vinculado") else False,
            })
        elif caminho == "/perfil":
            self._responder_json(perfil_mod.carregar_perfil())
        elif caminho == "/radar/atual":
            forcar = (params.get("forcar") or ["0"])[0] == "1"
            if not forcar and radar_mod.radar_ja_gerado_hoje():
                self._responder_json({"radar": radar_mod.obter_ultimo_radar(), "novo": False})
                return
            try:
                provedor = obter_provedor()
                perfil = perfil_mod.carregar_perfil()
                candidatos = _coletar_candidatos(provedor, perfil)
                radar = radar_mod.gerar_radar(candidatos)
                self._responder_json({"radar": radar, "novo": True})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e), "radar": []}, status=503)
        elif caminho == "/radar/historico":
            limite = int((params.get("limite") or [20])[0])
            self._responder_json(historico_mod.obter_historico(limite))
        else:
            self._responder_404()

    def do_POST(self):
        caminho = self.path
        corpo = _ler_corpo_json(self)

        if caminho == "/perfil/artista_favorito":
            self._responder_json(perfil_mod.adicionar_artista_favorito(corpo.get("nome", ""), corpo.get("genero")))
        elif caminho == "/perfil/artista_rejeitado":
            self._responder_json(perfil_mod.adicionar_artista_rejeitado(corpo.get("nome", "")))
        elif caminho == "/perfil/genero":
            self._responder_json(perfil_mod.definir_peso_genero(corpo.get("nome", ""), float(corpo.get("peso", 0.5))))
        elif caminho == "/perfil/discovery_level":
            self._responder_json(perfil_mod.definir_discovery_level(float(corpo.get("valor", 0.5))))
        elif caminho == "/radar/feedback":
            entrada = feedback_mod.processar_feedback(
                corpo.get("track_id", ""), corpo.get("feedback", ""), corpo.get("genero"),
            )
            if entrada is None:
                self._responder_404()
            else:
                self._responder_json(entrada)
        elif caminho == "/radar/proxima":
            # 🔥 Continuação ao vivo (Modo Música do ERIS, 2026-08-25) - UMA
            # sugestão semeada pela faixa tocando agora, não o lote semanal do
            # Radar. Ver echo/core/continuacao.py.
            try:
                provedor = obter_provedor()
                perfil = perfil_mod.carregar_perfil()
                proxima = continuacao_mod.sugerir_proxima(
                    provedor, perfil, corpo.get("artista_atual", ""), corpo.get("titulo_atual", ""), corpo.get("excluir", []),
                )
                self._responder_json({"proxima": proxima})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e), "proxima": None}, status=503)
        elif caminho == "/radar/feedback_ao_vivo":
            # 🔥 Botões 👍/👎 do Modo Música (ERIS, 2026-08-26) - a faixa tocada ao
            # vivo pode nunca ter passado pelo Radar; cria a entrada no histórico
            # na hora e resolve o gênero sozinho (o ERIS só manda artista/título).
            try:
                provedor = obter_provedor()
                entrada = feedback_mod.processar_feedback_ao_vivo(
                    provedor, corpo.get("titulo", ""), corpo.get("artista", ""), corpo.get("feedback", ""),
                )
                self._responder_json({"entrada": entrada})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e), "entrada": None}, status=503)
        elif caminho == "/radar/semente":
            # 🔥 Ponto de partida do `/caos` (ERIS, 2026-08-26) - sugestão SEM
            # faixa atual pra semear (diferente de `/radar/proxima`), mesma
            # coleta de 3 fontes do Radar semanal, mas com o teto reduzido
            # (usuário esperando AO VIVO - ver docstring de _coletar_candidatos,
            # achado real: essa chamada levava ~10s sem o corte).
            try:
                provedor = obter_provedor()
                perfil = perfil_mod.carregar_perfil()
                candidatos = _coletar_candidatos(provedor, perfil, limite_geral=15, max_artistas=1, max_generos=3)
                semente = continuacao_mod.sugerir_semente(candidatos, perfil, corpo.get("excluir", []))
                self._responder_json({"semente": semente})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e), "semente": None}, status=503)
        elif caminho == "/perfil/importar_historico":
            try:
                provedor = obter_provedor()
                limite = int(corpo.get("limite", 30))
                artistas = provedor.obter_top_artistas_usuario(limite=limite)
                perfil = perfil_mod.importar_favoritos_do_historico(artistas)
                self._responder_json({"perfil": perfil, "artistas_importados": len(artistas)})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e)}, status=503)
        elif caminho == "/perfil/importar_artistas":
            # 🔥 Cadastro em LOTE (2026-08-25, pedido do usuário - histórico de
            # scrobbling dele estava vazio, então precisava de um jeito manual de
            # colar uma lista/playlist já exportada). Reaproveita
            # adicionar_artista_favorito (flat, mesmo peso por artista - diferente
            # de importar_favoritos_do_historico, que pesa por RANKING real; aqui
            # a ordem da lista colada não representa preferência relativa
            # nenhuma, seria desonesto fingir que representa).
            try:
                nomes = [n.strip() for n in (corpo.get("nomes") or []) if n and n.strip()]
                provedor = obter_provedor()
                generos_por_nome = provedor.resolver_generos(nomes)
                for nome in nomes:
                    generos_artista = generos_por_nome.get(nome.lower(), [])
                    perfil_mod.adicionar_artista_favorito(nome, genero=generos_artista[0] if generos_artista else None)
                self._responder_json({"perfil": perfil_mod.carregar_perfil(), "artistas_importados": len(nomes)})
            except ProvedorIndisponivel as e:
                self._responder_json({"erro": str(e)}, status=503)
        else:
            self._responder_404()

    def log_message(self, format, *args):
        return


def iniciar_servidor_api():
    servidor = HTTPServer((LOCAL_API_HOST, LOCAL_API_PORT), _API)
    servidor.serve_forever()

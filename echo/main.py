# -*- coding: utf-8 -*-
"""Entry point standalone do ECHO (`python -m echo.main`) - Modo DJ da GAIA (perfil
musical, ranking determinístico, Radar Musical semanal). Processo próprio, sem loop de
manutenção (mesmo padrão do HESTIA): quem decide QUANDO gerar o Radar é a GAIA (via
Agendador Diário ou comando do usuário) - o ECHO só responde HTTP quando perguntado."""
import os
import socket
import sys

from dotenv import load_dotenv

# 🔥 override=True (mesmo bug real corrigido no HESTIA/GAIA, ver
# `Project G.A.I.A/assistant/docs/CORRECOES.md`) - sem isso, uma variável de ambiente
# herdada do processo que lançou o ECHO venceria o `.env` do ECHO em silêncio.
load_dotenv(override=True)

from echo.api_bridge import iniciar_servidor_api  # noqa: E402

PORTA_INSTANCIA_UNICA = 8775

_socket_instancia_unica = None


def _garantir_instancia_unica():
    global _socket_instancia_unica
    _socket_instancia_unica = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _socket_instancia_unica.bind(("127.0.0.1", PORTA_INSTANCIA_UNICA))
    except OSError:
        print(
            " [SISTEMA] Já existe uma instância do ECHO rodando "
            f"(porta {PORTA_INSTANCIA_UNICA} ocupada) - encerrando esta pra não rodar em duplicidade."
        )
        sys.exit(1)


def main():
    _garantir_instancia_unica()
    os.makedirs("data", exist_ok=True)

    print(" [SISTEMA] ECHO pronto - ponte HTTP na porta 8774 (sem loop próprio, GAIA decide quando gerar o Radar).")
    iniciar_servidor_api()  # bloqueia a thread principal


if __name__ == "__main__":
    main()

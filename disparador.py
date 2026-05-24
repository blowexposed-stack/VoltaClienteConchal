"""
disparador.py - Script de disparo automático de mensagens via WhatsApp
Execute este script diariamente (via cron job ou agendador de tarefas do Windows)
para enviar os lembretes cujo prazo venceu hoje.

Exemplo de cron job (Linux/Mac) - roda todo dia às 9h:
    0 9 * * * cd /caminho/do/projeto && python disparador.py

Exemplo de agendador Windows (Task Scheduler):
    Programa: python
    Argumentos: C:\caminho\do\projeto\disparador.py
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from database.models import buscar_agendamentos_para_hoje, marcar_como_enviado


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO DE ENVIO — SIMULADO (MOCK)
# Substitua a função abaixo pela integração real com sua API de WhatsApp
# ══════════════════════════════════════════════════════════════════════════════

def enviar_whatsapp(celular: str, mensagem: str, nome_cliente: str) -> bool:
    """
    🔧 FUNÇÃO SIMULADA — Apenas imprime no console o que seria enviado.

    ─────────────────────────────────────────────────────────────────────────
    INTEGRAÇÃO REAL: substitua o conteúdo desta função pela sua API preferida

    OPÇÃO 1 — Evolution API (self-hosted, gratuita):
        import requests
        url = "http://SEU_SERVIDOR/message/sendText/NOME_INSTANCIA"
        headers = {"apikey": "SUA_API_KEY", "Content-Type": "application/json"}
        payload = {
            "number": f"55{celular}@s.whatsapp.net",
            "text": mensagem
        }
        r = requests.post(url, json=payload, headers=headers)
        return r.status_code == 201

    OPÇÃO 2 — Z-API:
        url = f"https://api.z-api.io/instances/ID/token/TOKEN/send-text"
        payload = {"phone": f"55{celular}", "message": mensagem}
        r = requests.post(url, json=payload)
        return r.ok

    OPÇÃO 3 — Twilio WhatsApp:
        from twilio.rest import Client
        client = Client("ACCOUNT_SID", "AUTH_TOKEN")
        msg = client.messages.create(
            from_="whatsapp:+14155238886",
            body=mensagem,
            to=f"whatsapp:+55{celular}"
        )
        return msg.sid is not None
    ─────────────────────────────────────────────────────────────────────────
    """
    # ── SIMULAÇÃO: imprime no console ──
    print("\n" + "═" * 60)
    print(f"📱 [SIMULADO] Enviando WhatsApp para {nome_cliente}")
    print(f"   Número : +55 {celular}")
    print(f"   Mensagem:\n   {mensagem}")
    print("═" * 60)
    return True  # Retorna True para simular sucesso


# ══════════════════════════════════════════════════════════════════════════════
# ROTINA PRINCIPAL DE DISPARO
# ══════════════════════════════════════════════════════════════════════════════

def executar_disparos():
    """
    Verifica todos os agendamentos com prazo para hoje
    e executa o envio das mensagens.
    """
    hoje = datetime.now().strftime("%d/%m/%Y")
    print(f"\n🤖 Disparador iniciado — {hoje}")
    print("🔍 Buscando agendamentos para hoje...")

    agendamentos = buscar_agendamentos_para_hoje()

    if not agendamentos:
        print("✅ Nenhum lembrete para enviar hoje.")
        return

    print(f"📋 {len(agendamentos)} lembrete(s) encontrado(s).\n")

    enviados   = 0
    com_erro   = 0

    for ag in agendamentos:
        try:
            sucesso = enviar_whatsapp(
                celular=ag["cliente_celular"],
                mensagem=ag["mensagem_personalizada"],
                nome_cliente=ag["cliente_nome"]
            )

            if sucesso:
                marcar_como_enviado(ag["id"])
                enviados += 1
                print(f"   ✅ Enviado para {ag['cliente_nome']}")
            else:
                com_erro += 1
                print(f"   ❌ Falha ao enviar para {ag['cliente_nome']}")

        except Exception as e:
            com_erro += 1
            print(f"   ❌ Erro inesperado para {ag['cliente_nome']}: {e}")

    print(f"\n📊 Resumo: {enviados} enviado(s) | {com_erro} erro(s)")
    print("🏁 Disparador finalizado.\n")


if __name__ == "__main__":
    executar_disparos()

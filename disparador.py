"""
disparador.py — Disparo automático de lembretes via WhatsApp

Cron job diário recomendado (ex: 9h):
  0 9 * * * cd /caminho/projeto && python disparador.py

Lógica:
  - Busca todos os agendamentos com data_envio == hoje e enviado == 0
  - Se mensagem_personalizada == '__IA__': pede à IA gerar a mensagem na hora
  - Senão: usa a mensagem salva
  - Envia via Evolution API (ou simula se EVOLUTION_URL não estiver configurado)
"""

import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from database.models import buscar_agendamentos_para_hoje, marcar_como_enviado
import requests as http

EVOLUTION_URL    = os.environ.get("EVOLUTION_URL", "")
EVOLUTION_APIKEY = os.environ.get("EVOLUTION_APIKEY", "")
EVOLUTION_INST   = os.environ.get("EVOLUTION_INST", "")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
BASE_URL         = os.environ.get("BASE_URL", "http://localhost:5000")


def enviar_whatsapp(celular: str, mensagem: str, nome: str) -> bool:
    if not EVOLUTION_URL:
        print(f"\n{'═'*58}")
        print(f"📱 [SIMULADO] {nome} ({celular})")
        print(f"   {mensagem[:120]}")
        print('═'*58)
        return True
    try:
        r = http.post(
            f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INST}",
            headers={"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"},
            json={"number": f"55{celular}@s.whatsapp.net", "text": mensagem},
            timeout=10,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"   [WA-ERRO] {e}")
        return False


def gerar_mensagem_ia(nome: str, servico: str, nome_comercio: str, link: str) -> str:
    servico_fmt = servico if servico else "atendimento"
    fallback = (
        f"Olá {nome}! 😊 Já faz um tempinho desde o seu último {servico_fmt}. "
        f"Que tal agendar novamente? Acesse: {link}"
    )
    if not ANTHROPIC_KEY:
        return fallback

    prompt = f"""Você é assistente do estabelecimento "{nome_comercio}".
Escreva UMA mensagem de WhatsApp (máximo 3 linhas) lembrando o cliente de agendar novamente.

Cliente: {nome}
Último serviço: {servico_fmt}
Link de agendamento: {link}

Regras:
- Tom amigável e informal, português brasileiro
- Mencione o nome e o serviço
- Inclua o link no final
- Máximo 1 emoji
- Retorne APENAS o texto, sem aspas ou explicações"""

    try:
        resp = http.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514",
                  "max_tokens": 200,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=15,
        )
        texto = resp.json()["content"][0]["text"].strip()
        if link not in texto:
            texto += f"\n{link}"
        return texto
    except Exception as e:
        print(f"   [IA-ERRO] {e} — usando mensagem padrão")
        return fallback


def executar():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n🤖 Disparador iniciado — {agora}")
    print("─" * 55)

    agendamentos = buscar_agendamentos_para_hoje()
    if not agendamentos:
        print("✅ Nenhum lembrete para hoje.")
        print("🏁 Finalizado.\n")
        return

    print(f"📋 {len(agendamentos)} lembrete(s) encontrado(s).\n")
    enviados = erros = 0

    for ag in agendamentos:
        nome    = ag["cliente_nome"]
        celular = ag["cliente_celular"]
        servico = ag.get("cliente_servico") or ""
        slug    = ag.get("slug") or ""
        link    = f"{BASE_URL}/agendar/{slug}" if slug else BASE_URL
        comercio = ag.get("nome_comercio") or "nosso estabelecimento"

        # Gera mensagem via IA se marcada como __IA__
        if ag["mensagem_personalizada"] == "__IA__":
            print(f"   🤖 Gerando mensagem IA para {nome}…")
            mensagem = gerar_mensagem_ia(nome, servico, comercio, link)
        else:
            mensagem = ag["mensagem_personalizada"] or ""

        if not mensagem:
            erros += 1
            print(f"   ❌ Mensagem vazia para {nome}")
            continue

        ok = enviar_whatsapp(celular, mensagem, nome)
        if ok:
            marcar_como_enviado(ag["id"])
            enviados += 1
            print(f"   ✅ Enviado → {nome}")
        else:
            erros += 1
            print(f"   ❌ Falha → {nome}")

    print(f"\n📊 Resumo: {enviados} enviado(s) | {erros} erro(s)")
    print("🏁 Disparador finalizado.\n")


if __name__ == "__main__":
    executar()

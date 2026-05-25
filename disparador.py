"""
app.py — Backend Flask do VoltaCliente Conchal

Rotas:
  GET  /                    → redireciona para /login
  GET  /login               → tela de acesso
  POST /registrar           → criação de conta
  POST /login               → autenticação
  GET  /logout              → encerrar sessão
  GET  /dashboard           → painel principal (requer acesso)
  POST /salvar_cliente      → cadastra cliente + lembrete
  POST /salvar_horario      → adiciona horário livre na agenda
  POST /deletar_horario     → remove horário
  GET  /agendar/<slug>      → agenda pública (cliente final)
  POST /agendar/<slug>      → submissão do agendamento público
  POST /webhook/<slug>      → webhook Evolution API (IA + handoff)
  GET  /pagamento           → tela de assinatura
  POST /webhook_pagamento   → callback Mercado Pago
  GET  /404                 → página de erro customizada
"""

import os
import json
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, abort
)
import requests as http

from database.models import (
    init_db,
    demo_iniciar, demo_expirado, demo_segundos_restantes,
    criar_usuario, buscar_usuario_por_email,
    buscar_usuario_por_id, buscar_usuario_por_slug,
    usuario_tem_acesso, ativar_assinatura, salvar_whatsapp_usuario,
    listar_clientes, criar_cliente,
    listar_agendamentos, criar_agendamento,
    buscar_agendamentos_para_hoje, marcar_como_enviado,
    listar_horarios, criar_horario, deletar_horario,
    criar_agendamento_publico, listar_agendamentos_publicos,
    ia_esta_pausada, pausar_ia, retomar_ia,
    salvar_mensagem, buscar_historico,
)
from notificacoes import notificar_login_admin

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


# ── Configurações via variáveis de ambiente ────────────────────────────────
MP_ACCESS_TOKEN   = os.environ.get("MP_ACCESS_TOKEN", "")
MP_CHECKOUT_URL   = os.environ.get("MP_CHECKOUT_URL", "#")
PLANO_VALOR       = os.environ.get("PLANO_VALOR", "R$ 30,00")

# Evolution API
EVOLUTION_URL     = os.environ.get("EVOLUTION_URL", "")
EVOLUTION_APIKEY  = os.environ.get("EVOLUTION_APIKEY", "")
EVOLUTION_INST    = os.environ.get("EVOLUTION_INST", "")

# Anthropic (IA)
ANTHROPIC_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS / DECORATORS
# ══════════════════════════════════════════════════════════════════════════════

def ip_cliente():
    """Retorna o IP real mesmo atrás de proxy (Render/Heroku)."""
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "0.0.0.0"
    )


def usuario_logado():
    uid = session.get("usuario_id")
    if not uid:
        return None
    return buscar_usuario_por_id(uid)


def requer_login(f):
    """Decorator: exige sessão ativa."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("pagina_login"))
        return f(*args, **kwargs)
    return wrapper


def requer_acesso(f):
    """Decorator: exige login + trial/assinatura válidos."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        usuario = usuario_logado()
        if not usuario:
            return redirect(url_for("pagina_login"))
        if not usuario_tem_acesso(usuario):
            return redirect(url_for("pagina_pagamento"))
        return f(*args, **kwargs)
    return wrapper


def enviar_whatsapp(celular: str, mensagem: str) -> bool:
    """
    Envia mensagem via Evolution API.
    Se EVOLUTION_URL não estiver configurado, apenas imprime (modo dev).
    """
    if not EVOLUTION_URL:
        print(f"[WA-SIMULADO] → {celular}: {mensagem}")
        return True
    try:
        url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INST}"
        headers = {"apikey": EVOLUTION_APIKEY, "Content-Type": "application/json"}
        payload = {
            "number": f"55{celular}@s.whatsapp.net",
            "text": mensagem,
        }
        r = http.post(url, json=payload, headers=headers, timeout=10)
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[WA-ERRO] {e}")
        return False


def resposta_ia(usuario, celular: str, mensagem_usuario: str) -> str:
    """
    Chama a API da Anthropic para gerar a resposta da IA.
    Retorna string vazia se ANTHROPIC_API_KEY não estiver configurada.
    """
    if not ANTHROPIC_KEY:
        return ""

    historico = buscar_historico(usuario["id"], celular, limite=8)
    slug = usuario["slug"] or ""
    link_agendamento = f"{request.host_url}agendar/{slug}"
    nome_comercio = usuario["nome_comercio"] or "nosso estabelecimento"

    system_prompt = f"""Você é a assistente virtual de atendimento do(a) {nome_comercio}.
Seu único objetivo é identificar pedidos de agendamento e enviar o link de agendamento.
Link de agendamento: {link_agendamento}

Regras:
- Se o cliente quiser agendar → envie o link e diga para clicar nele.
- Se tiver dúvidas sobre horários ou serviços → responda brevemente e ofereça o link.
- Seja cordial, breve e em português brasileiro.
- Nunca invente horários; direcione sempre ao link.
- Se o cliente disser que o link não abre, oriente-o a copiar e colar no navegador."""

    mensagens = []
    for h in historico:
        mensagens.append({"role": h["role"], "content": h["conteudo"]})
    mensagens.append({"role": "user", "content": mensagem_usuario})

    try:
        resp = http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "system": system_prompt,
                "messages": mensagens,
            },
            timeout=15,
        )
        data = resp.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"[IA-ERRO] {e}")
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS PÚBLICAS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return redirect(url_for("pagina_login"))


@app.route("/login", methods=["GET"])
def pagina_login():
    ip = ip_cliente()
    demo_iniciar(ip)
    segundos = demo_segundos_restantes(ip)
    return render_template(
        "login.html",
        demo_seconds_remaining=segundos,
        checkout_url=MP_CHECKOUT_URL,
    )


@app.route("/login", methods=["POST"])
def fazer_login():
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "").strip()

    usuario = buscar_usuario_por_email(email)
    if not usuario or usuario["senha"] != senha:
        flash("E-mail ou senha incorretos.", "erro")
        return redirect(url_for("pagina_login"))

    session["usuario_id"] = usuario["id"]
    notificar_login_admin(usuario, metodo="formulario")
    return redirect(url_for("dashboard"))


@app.route("/registrar", methods=["POST"])
def registrar():
    nome         = request.form.get("nome", "").strip()
    nome_comercio = request.form.get("nome_comercio", "").strip()
    email        = request.form.get("email", "").strip().lower()
    senha        = request.form.get("senha", "").strip()
    ip           = ip_cliente()

    if not nome or not email or not senha:
        flash("Preencha todos os campos obrigatórios.", "erro")
        return redirect(url_for("pagina_login"))

    usuario = criar_usuario(nome, nome_comercio, email, senha, ip)
    if not usuario:
        flash("Este e-mail ou IP já possui uma conta cadastrada.", "erro")
        return redirect(url_for("pagina_login"))

    session["usuario_id"] = usuario["id"]
    notificar_login_admin(usuario, metodo="cadastro")
    flash(f"Bem-vindo, {nome}! Seu trial de 7 dias está ativo.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/dashboard_demo")
def dashboard_demo():
    """Acesso livre por 10 minutos sem login (bloqueado por IP)."""
    ip = ip_cliente()
    if demo_expirado(ip):
        flash("Seu tempo de demonstração acabou. Crie uma conta para ganhar 7 dias grátis!", "erro")
        return redirect(url_for("pagina_login"))
    # Usa usuário demo
    usuario = buscar_usuario_por_email("admin@demo.com")
    clientes     = listar_clientes(usuario["id"])
    agendamentos = listar_agendamentos(usuario["id"])
    horarios     = listar_horarios(usuario["id"])
    agend_pub    = listar_agendamentos_publicos(usuario["id"])
    return render_template(
        "dashboard.html",
        usuario=usuario,
        clientes=clientes,
        agendamentos=agendamentos,
        horarios=horarios,
        agendamentos_publicos=agend_pub,
        demo=True,
        demo_seconds_remaining=demo_segundos_restantes(ip),
        link_bio=_link_bio(usuario),
    )


@app.route("/dashboard")
@requer_acesso
def dashboard():
    usuario      = usuario_logado()
    clientes     = listar_clientes(usuario["id"])
    agendamentos = listar_agendamentos(usuario["id"])
    horarios     = listar_horarios(usuario["id"])
    agend_pub    = listar_agendamentos_publicos(usuario["id"])
    return render_template(
        "dashboard.html",
        usuario=usuario,
        clientes=clientes,
        agendamentos=agendamentos,
        horarios=horarios,
        agendamentos_publicos=agend_pub,
        demo=False,
        demo_seconds_remaining=0,
        link_bio=_link_bio(usuario),
    )


def _link_bio(usuario) -> str:
    """Gera o link da bio para o Instagram/WhatsApp do dono."""
    if not usuario["slug"]:
        return ""
    base = os.environ.get("BASE_URL", request.host_url.rstrip("/"))
    return f"{base}/agendar/{usuario['slug']}"


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("pagina_login"))


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS DO PAINEL (requerem acesso)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/salvar_cliente", methods=["POST"])
@requer_acesso
def salvar_cliente():
    usuario  = usuario_logado()
    nome     = request.form.get("nome", "").strip()
    celular  = request.form.get("celular", "").strip()
    servico  = request.form.get("servico", "").strip()
    data_env = request.form.get("data_envio", "").strip()
    mensagem = request.form.get("mensagem", "").strip()

    if not nome or not celular or not data_env or not mensagem:
        flash("Preencha todos os campos do cliente.", "erro")
        return redirect(url_for("dashboard"))

    cliente_id = criar_cliente(usuario["id"], nome, celular, servico)
    criar_agendamento(
        usuario["id"], nome, celular, mensagem, data_env, cliente_id
    )
    flash(f"Cliente {nome} cadastrado com lembrete para {data_env}.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/salvar_horario", methods=["POST"])
@requer_acesso
def salvar_horario():
    usuario    = usuario_logado()
    data       = request.form.get("data", "").strip()
    hora_inicio = request.form.get("hora_inicio", "").strip()

    if not data or not hora_inicio:
        flash("Informe data e hora.", "erro")
        return redirect(url_for("dashboard"))

    criar_horario(usuario["id"], data, hora_inicio)
    flash(f"Horário {data} às {hora_inicio} adicionado.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/deletar_horario", methods=["POST"])
@requer_acesso
def rota_deletar_horario():
    usuario    = usuario_logado()
    horario_id = request.form.get("horario_id", type=int)
    if horario_id:
        deletar_horario(horario_id, usuario["id"])
        flash("Horário removido.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/salvar_whatsapp", methods=["POST"])
@requer_acesso
def salvar_whatsapp():
    usuario = usuario_logado()
    numero  = request.form.get("whatsapp", "").strip()
    salvar_whatsapp_usuario(usuario["id"], numero)
    flash("Número WhatsApp salvo.", "sucesso")
    return redirect(url_for("dashboard"))


# ══════════════════════════════════════════════════════════════════════════════
# AGENDA PÚBLICA (cliente final)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/agendar/<slug>", methods=["GET", "POST"])
def agenda_publica(slug):
    usuario = buscar_usuario_por_slug(slug)
    if not usuario:
        abort(404)

    horarios_livres = listar_horarios(usuario["id"], apenas_livres=True)

    if request.method == "POST":
        nome       = request.form.get("nome", "").strip()
        celular    = request.form.get("celular", "").strip()
        servico    = request.form.get("servico", "").strip()
        horario_id = request.form.get("horario_id", type=int)

        if not nome or not celular or not horario_id:
            flash("Preencha nome, WhatsApp e escolha um horário.", "erro")
            return render_template("agenda_publica.html", usuario=usuario,
                                   horarios=horarios_livres)

        criar_agendamento_publico(usuario["id"], horario_id, nome, celular, servico)

        # Notifica o dono via WhatsApp
        if usuario["whatsapp"]:
            msg_dono = (
                f"📅 Novo agendamento!\n"
                f"Cliente: {nome}\n"
                f"WhatsApp: {celular}\n"
                f"Serviço: {servico or 'não informado'}"
            )
            enviar_whatsapp(usuario["whatsapp"], msg_dono)

        flash(f"Agendamento confirmado! Até breve, {nome}.", "sucesso")
        return redirect(url_for("agenda_publica", slug=slug))

    return render_template("agenda_publica.html", usuario=usuario,
                           horarios=horarios_livres)


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK EVOLUTION API — IA + HANDOFF
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/webhook/<slug>", methods=["POST"])
def webhook_whatsapp(slug):
    """
    Recebe eventos da Evolution API para o estabelecimento identificado pelo slug.

    Payload esperado (mensagens recebidas):
    {
      "event": "messages.upsert",
      "data": {
        "key": { "fromMe": false, "remoteJid": "5519...@s.whatsapp.net" },
        "message": { "conversation": "texto da mensagem" }
      }
    }

    Quando fromMe = true → o dono está digitando → pausar IA por 12h.
    """
    usuario = buscar_usuario_por_slug(slug)
    if not usuario:
        return jsonify({"ok": False, "erro": "slug inválido"}), 404

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"ok": False}), 400

    event = payload.get("event", "")
    data  = payload.get("data", {})

    if event != "messages.upsert":
        return jsonify({"ok": True, "ignorado": True})

    key        = data.get("key", {})
    from_me    = key.get("fromMe", False)
    remote_jid = key.get("remoteJid", "")

    # Extrai número limpo (sem @s.whatsapp.net e sem "55")
    celular = remote_jid.replace("@s.whatsapp.net", "").replace("@c.us", "")

    # ── HANDOFF: dono digitou → pausar IA ────────────────────────────────
    if from_me:
        pausar_ia(usuario["id"], celular)
        return jsonify({"ok": True, "acao": "ia_pausada"})

    # ── IA PAUSADA → silêncio ─────────────────────────────────────────────
    if ia_esta_pausada(usuario["id"], celular):
        return jsonify({"ok": True, "acao": "silencio_handoff"})

    # ── Extrai texto da mensagem ──────────────────────────────────────────
    msg_obj = data.get("message", {})
    texto   = (
        msg_obj.get("conversation")
        or msg_obj.get("extendedTextMessage", {}).get("text")
        or ""
    ).strip()

    if not texto:
        return jsonify({"ok": True, "ignorado": True})

    # ── Salva mensagem do usuário e gera resposta IA ──────────────────────
    salvar_mensagem(usuario["id"], celular, "user", texto)
    resposta = resposta_ia(usuario, celular, texto)

    if resposta:
        salvar_mensagem(usuario["id"], celular, "assistant", resposta)
        enviar_whatsapp(celular, resposta)
        return jsonify({"ok": True, "acao": "ia_respondeu"})

    return jsonify({"ok": True, "acao": "ia_sem_chave"})


# ══════════════════════════════════════════════════════════════════════════════
# PAGAMENTO / ASSINATURA
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/pagamento")
@requer_login
def pagina_pagamento():
    return render_template(
        "pagamento.html",
        valor=PLANO_VALOR,
        checkout_url=MP_CHECKOUT_URL,
    )


@app.route("/webhook_pagamento", methods=["POST"])
def webhook_pagamento():
    """
    Callback do Mercado Pago para assinaturas aprovadas.
    Configure a URL no painel do MP: https://seuapp.com/webhook_pagamento
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        action = data.get("action", "")
        if action not in ("payment.created", "payment.updated"):
            return jsonify({"ok": True})

        payment_id = data.get("data", {}).get("id")
        if not payment_id or not MP_ACCESS_TOKEN:
            return jsonify({"ok": True})

        # Consulta o pagamento no MP
        resp = http.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"},
            timeout=10,
        )
        pagamento = resp.json()
        status    = pagamento.get("status")
        email     = pagamento.get("payer", {}).get("email", "")

        if status == "approved" and email:
            usuario = buscar_usuario_por_email(email)
            if usuario:
                ativar_assinatura(usuario["id"])

        return jsonify({"ok": True})
    except Exception as e:
        print(f"[WEBHOOK-MP] Erro: {e}")
        return jsonify({"ok": False}), 500


# ══════════════════════════════════════════════════════════════════════════════
# ERROS
# ══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def pagina_404(e):
    return render_template("404.html"), 404


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

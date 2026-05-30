"""
app.py — Backend Flask do VoltaCliente Conchal
"""

import os
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, abort
)
import requests as http

from database.models import (
    init_db, CICLOS_PADRAO,
    demo_iniciar, demo_expirado, demo_segundos_restantes,
    criar_usuario, buscar_usuario_por_email,
    buscar_usuario_por_id, buscar_usuario_por_slug,
    usuario_tem_acesso, ativar_assinatura, salvar_whatsapp_usuario,
    listar_clientes, criar_cliente, criar_lembretes_ciclo,
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

MP_ACCESS_TOKEN  = os.environ.get("MP_ACCESS_TOKEN", "")
MP_CHECKOUT_URL  = os.environ.get("MP_CHECKOUT_URL", "#")
PLANO_VALOR      = os.environ.get("PLANO_VALOR", "R$ 30,00")
EVOLUTION_URL    = os.environ.get("EVOLUTION_URL", "")
EVOLUTION_APIKEY = os.environ.get("EVOLUTION_APIKEY", "")
EVOLUTION_INST   = os.environ.get("EVOLUTION_INST", "")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def ip_cliente():
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr or "0.0.0.0"
    )

def usuario_logado():
    uid = session.get("usuario_id")
    return buscar_usuario_por_id(uid) if uid else None

def requer_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("pagina_login"))
        return f(*args, **kwargs)
    return wrapper

def requer_acesso(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        u = usuario_logado()
        if not u:
            return redirect(url_for("pagina_login"))
        if not usuario_tem_acesso(u):
            return redirect(url_for("pagina_pagamento"))
        return f(*args, **kwargs)
    return wrapper

def _link_bio(usuario) -> str:
    if not usuario or not usuario["slug"]:
        return ""
    base = os.environ.get("BASE_URL", request.host_url.rstrip("/"))
    return f"{base}/agendar/{usuario['slug']}"

def enviar_whatsapp(celular: str, mensagem: str) -> bool:
    if not EVOLUTION_URL:
        print(f"[WA-SIMULADO] {celular}: {mensagem[:60]}...")
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
        print(f"[WA-ERRO] {e}")
        return False

def resposta_ia(usuario, celular: str, texto_usuario: str) -> str:
    if not ANTHROPIC_KEY:
        return ""
    historico     = buscar_historico(usuario["id"], celular, limite=8)
    nome_comercio = usuario["nome_comercio"] or "nosso estabelecimento"
    link_agenda   = _link_bio(usuario)

    system = f"""Você é a assistente virtual do(a) {nome_comercio}.
Seu objetivo é atender clientes pelo WhatsApp e direcioná-los ao link de agendamento.
Link de agendamento: {link_agenda}

Regras:
- Pedido de agendamento → envie o link e peça para clicar.
- Dúvidas sobre serviços/horários → responda brevemente e ofereça o link.
- Tom cordial e informal, português brasileiro.
- Nunca invente horários ou preços.
- Se o link não abrir → oriente a copiar e colar no navegador."""

    msgs = [{"role": h["role"], "content": h["conteudo"]} for h in historico]
    msgs.append({"role": "user", "content": texto_usuario})

    try:
        resp = http.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514",
                  "max_tokens": 300, "system": system, "messages": msgs},
            timeout=15,
        )
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"[IA-ERRO] {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# ROTAS PÚBLICAS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return redirect(url_for("pagina_login"))


@app.route("/login", methods=["GET"])
def pagina_login():
    ip = ip_cliente()
    demo_iniciar(ip)  # idempotente — F5 não reinicia o clock
    return render_template("login.html",
                           demo_seconds_remaining=demo_segundos_restantes(ip),
                           checkout_url=MP_CHECKOUT_URL)


@app.route("/login", methods=["POST"])
def fazer_login():
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "").strip()
    u = buscar_usuario_por_email(email)
    if not u or u["senha"] != senha:
        flash("E-mail ou senha incorretos.", "erro")
        return redirect(url_for("pagina_login"))
    session["usuario_id"] = u["id"]
    notificar_login_admin(u, metodo="formulario")
    return redirect(url_for("dashboard"))


@app.route("/registrar", methods=["POST"])
def registrar():
    nome          = request.form.get("nome", "").strip()
    nome_comercio = request.form.get("nome_comercio", "").strip()
    email         = request.form.get("email", "").strip().lower()
    senha         = request.form.get("senha", "").strip()
    ip            = ip_cliente()

    if not nome or not email or not senha:
        flash("Preencha todos os campos obrigatórios.", "erro")
        return redirect(url_for("pagina_login"))

    u = criar_usuario(nome, nome_comercio, email, senha, ip)
    if not u:
        flash("Este e-mail ou IP já possui uma conta cadastrada.", "erro")
        return redirect(url_for("pagina_login"))

    session["usuario_id"] = u["id"]
    notificar_login_admin(u, metodo="cadastro")
    flash(f"Bem-vindo(a), {nome}! Seu trial de 7 dias está ativo.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("pagina_login"))


# ── Demo (somente leitura, bloqueado por IP + F5 prova) ───────────────────
@app.route("/dashboard_demo")
def dashboard_demo():
    ip = ip_cliente()
    # Garante que o clock está rodando — idempotente
    demo_iniciar(ip)
    if demo_expirado(ip):
        flash("Seu tempo de demonstração acabou. Crie uma conta e ganhe 7 dias grátis!", "erro")
        return redirect(url_for("pagina_login"))
    u        = buscar_usuario_por_email("admin@demo.com")
    segundos = demo_segundos_restantes(ip)
    return render_template("dashboard.html",
        usuario=u,
        clientes=listar_clientes(u["id"]),
        agendamentos=listar_agendamentos(u["id"]),
        horarios=listar_horarios(u["id"]),
        agendamentos_publicos=listar_agendamentos_publicos(u["id"]),
        demo=True,
        demo_seconds_remaining=segundos,
        link_bio=_link_bio(u),
        ciclos_padrao=CICLOS_PADRAO,
    )


# ── Dashboard real ─────────────────────────────────────────────────────────
@app.route("/dashboard")
@requer_acesso
def dashboard():
    u = usuario_logado()
    return render_template("dashboard.html",
        usuario=u,
        clientes=listar_clientes(u["id"]),
        agendamentos=listar_agendamentos(u["id"]),
        horarios=listar_horarios(u["id"]),
        agendamentos_publicos=listar_agendamentos_publicos(u["id"]),
        demo=False,
        demo_seconds_remaining=0,
        link_bio=_link_bio(u),
        ciclos_padrao=CICLOS_PADRAO,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ROTAS DO PAINEL
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/salvar_cliente", methods=["POST"])
@requer_acesso
def salvar_cliente():
    u       = usuario_logado()
    nome    = request.form.get("nome", "").strip()
    celular = request.form.get("celular", "").strip()
    servico = request.form.get("servico", "").strip()
    # Ciclos: checkboxes com name="ciclo" e values "7","15","30"
    ciclos_raw = request.form.getlist("ciclo")
    ciclos = sorted({int(c) for c in ciclos_raw if c.isdigit()}) or CICLOS_PADRAO

    if not nome or not celular:
        flash("Preencha nome e WhatsApp do cliente.", "erro")
        return redirect(url_for("dashboard"))

    cliente_id = criar_cliente(u["id"], nome, celular, servico)
    criar_lembretes_ciclo(u["id"], cliente_id, nome, celular, ciclos)

    datas = ", ".join(
        (datetime.now() + __import__("datetime").timedelta(days=d)).strftime("%d/%m")
        for d in ciclos
    )
    flash(f"Cliente {nome} cadastrado. Lembretes agendados para: {datas}.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/salvar_whatsapp", methods=["POST"])
@requer_acesso
def salvar_whatsapp():
    u      = usuario_logado()
    numero = request.form.get("whatsapp", "").strip()
    salvar_whatsapp_usuario(u["id"], numero)
    flash("Número WhatsApp do negócio salvo com sucesso.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/salvar_horario", methods=["POST"])
@requer_acesso
def salvar_horario():
    u          = usuario_logado()
    data       = request.form.get("data", "").strip()
    hora_inicio = request.form.get("hora_inicio", "").strip()
    if not data or not hora_inicio:
        flash("Informe data e hora.", "erro")
        return redirect(url_for("dashboard"))
    criar_horario(u["id"], data, hora_inicio)
    flash(f"Horário {data} às {hora_inicio} adicionado.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/deletar_horario", methods=["POST"])
@requer_acesso
def rota_deletar_horario():
    u          = usuario_logado()
    horario_id = request.form.get("horario_id", type=int)
    if horario_id:
        deletar_horario(horario_id, u["id"])
        flash("Horário removido.", "sucesso")
    return redirect(url_for("dashboard"))


# ═══════════════════════════════════════════════════════════════════════════
# AGENDA PÚBLICA
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/agendar/<slug>", methods=["GET", "POST"])
def agenda_publica(slug):
    u = buscar_usuario_por_slug(slug)
    if not u:
        abort(404)

    horarios_livres = listar_horarios(u["id"], apenas_livres=True)

    if request.method == "POST":
        nome       = request.form.get("nome", "").strip()
        celular    = request.form.get("celular", "").strip()
        servico    = request.form.get("servico", "").strip()
        horario_id = request.form.get("horario_id", type=int)

        if not nome or not celular or not horario_id:
            flash("Preencha nome, WhatsApp e escolha um horário.", "erro")
            return render_template("agenda_publica.html", usuario=u,
                                   horarios=horarios_livres)

        criar_agendamento_publico(u["id"], horario_id, nome, celular, servico)

        # Notifica o dono
        if u["whatsapp"]:
            enviar_whatsapp(u["whatsapp"],
                f"📅 Novo agendamento!\nCliente: {nome}\nWhatsApp: {celular}"
                f"\nServiço: {servico or 'não informado'}")

        flash(f"Agendamento confirmado! Até breve, {nome} 🎉", "sucesso")
        return redirect(url_for("agenda_publica", slug=slug))

    return render_template("agenda_publica.html", usuario=u, horarios=horarios_livres)


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK EVOLUTION API — IA + HANDOFF
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/webhook/<slug>", methods=["POST"])
def webhook_whatsapp(slug):
    u = buscar_usuario_por_slug(slug)
    if not u:
        return jsonify({"ok": False}), 404

    payload = request.get_json(force=True, silent=True) or {}
    if payload.get("event") != "messages.upsert":
        return jsonify({"ok": True, "ignorado": True})

    key        = payload.get("data", {}).get("key", {})
    from_me    = key.get("fromMe", False)
    remote_jid = key.get("remoteJid", "")
    celular    = remote_jid.replace("@s.whatsapp.net", "").replace("@c.us", "")

    # Dono digitou → pausa IA por 12h
    if from_me:
        pausar_ia(u["id"], celular)
        return jsonify({"ok": True, "acao": "ia_pausada"})

    # IA em silêncio (handoff ativo)
    if ia_esta_pausada(u["id"], celular):
        return jsonify({"ok": True, "acao": "silencio_handoff"})

    msg_obj = payload.get("data", {}).get("message", {})
    texto   = (msg_obj.get("conversation")
               or msg_obj.get("extendedTextMessage", {}).get("text")
               or "").strip()
    if not texto:
        return jsonify({"ok": True, "ignorado": True})

    salvar_mensagem(u["id"], celular, "user", texto)
    resposta = resposta_ia(u, celular, texto)
    if resposta:
        salvar_mensagem(u["id"], celular, "assistant", resposta)
        enviar_whatsapp(celular, resposta)
        return jsonify({"ok": True, "acao": "ia_respondeu"})

    return jsonify({"ok": True, "acao": "ia_sem_chave"})


# ═══════════════════════════════════════════════════════════════════════════
# PAGAMENTO
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/pagamento")
@requer_login
def pagina_pagamento():
    return render_template("pagamento.html",
                           valor=PLANO_VALOR,
                           checkout_url=MP_CHECKOUT_URL)


@app.route("/webhook_pagamento", methods=["POST"])
def webhook_pagamento():
    try:
        data   = request.get_json(force=True, silent=True) or {}
        action = data.get("action", "")
        if action not in ("payment.created", "payment.updated"):
            return jsonify({"ok": True})
        payment_id = data.get("data", {}).get("id")
        if not payment_id or not MP_ACCESS_TOKEN:
            return jsonify({"ok": True})
        resp     = http.get(f"https://api.mercadopago.com/v1/payments/{payment_id}",
                            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}, timeout=10)
        pagto    = resp.json()
        if pagto.get("status") == "approved":
            email = pagto.get("payer", {}).get("email", "")
            uu    = buscar_usuario_por_email(email)
            if uu:
                ativar_assinatura(uu["id"])
        return jsonify({"ok": True})
    except Exception as e:
        print(f"[MP-WEBHOOK] {e}")
        return jsonify({"ok": False}), 500


@app.errorhandler(404)
def pagina_404(e):
    return render_template("404.html"), 404


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG","0")=="1")

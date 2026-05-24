"""
app.py - Backend principal do VoltaCliente Conchal.

Fluxo de acesso:
- Visitante anonimo usa por 10 minutos.
- Depois precisa criar conta/entrar.
- Conta nova recebe 7 dias gratis.
- Trial vencido bloqueia o sistema e envia para pagamento recorrente.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote_plus

from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, session, url_for
)

sys.path.insert(0, os.path.dirname(__file__))
from database.models import (
    buscar_usuario_por_email,
    buscar_usuario_por_id,
    buscar_usuario_por_slug,
    cancelar_agendamento_cliente,
    criar_cliente_e_agendamento,
    criar_agendamento_publico,
    criar_usuario_trial,
    garantir_horarios_padrao,
    init_db,
    listar_agendamentos,
    listar_agendamentos_clientes,
    listar_historico,
    listar_horarios_livres,
    registrar_login,
    status_plano_usuario,
    atualizar_whatsapp_profissional,
    buscar_estado_conversa,
    atualizar_estado_conversa,
    listar_conversas_ia,
)
from notificacoes import enviar_email_simples, notificar_login_admin


app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "sua-chave-secreta-local-troque-em-producao",
)
app.permanent_session_lifetime = timedelta(days=30)

DEMO_SECONDS = 10 * 60
DEMO_USER_ID = 1
MERCADO_PAGO_CHECKOUT_URL = os.environ.get(
    "MERCADO_PAGO_CHECKOUT_URL",
    "https://www.mercadopago.com.br/subscriptions/checkout?preapproval_plan_id=e7620a7230d34fd3a57672a36263ea9b",
)

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
)


def chamar_gemini(mensagem_cliente: str, nome_comercio: str) -> str:
    """
    Envia a mensagem do cliente para o Gemini e retorna a resposta da IA.
    Instrui a IA a se comportar como atendente do estabelecimento.
    """
    if not GEMINI_API_KEY:
        return "Olá! Recebemos sua mensagem. Em breve alguém do nosso time irá te responder! 😊"

    prompt_sistema = (
        f"Você é a assistente virtual do estabelecimento '{nome_comercio}'. "
        "Seu papel é recepcionar novos clientes que chegaram pelo link do WhatsApp, "
        "de forma simpática, curta e profissional. "
        "Responda em português do Brasil. "
        "Não invente informações sobre preços ou horários. "
        "Diga que já vamos verificar e responder em breve. "
        "Seja breve, amigável e use emojis de forma moderada."
    )

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt_sistema}]},
            {"role": "model", "parts": [{"text": "Entendido! Estou pronto para atender."}]},
            {"role": "user", "parts": [{"text": mensagem_cliente}]},
        ]
    }

    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            timeout=10,
        )
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[GEMINI] Erro: {e}")
        return "Olá! Recebemos sua mensagem e em breve iremos responder. 😊"


with app.app_context():
    init_db()


def usuario_atual():
    """Retorna o usuario logado na sessao."""
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    return buscar_usuario_por_id(usuario_id)


def iniciar_demo_se_preciso():
    """
    Inicia a degustacao anonima por 10 minutos.
    A sessao e permanente por 30 dias, entao fechar/abrir o navegador nao
    reinicia o tempo dentro do mesmo navegador.
    """
    if session.get("usuario_id"):
        return
    session.permanent = True
    if "demo_started_at" not in session:
        agora = datetime.utcnow()
        session["demo_started_at"] = agora.isoformat(timespec="seconds")
        session["demo_expires_at"] = (
            agora + timedelta(seconds=DEMO_SECONDS)
        ).isoformat(timespec="seconds")


def segundos_demo_restantes():
    """Retorna quantos segundos restam da degustacao anonima."""
    iniciar_demo_se_preciso()
    try:
        expira = datetime.fromisoformat(session["demo_expires_at"])
    except (KeyError, ValueError):
        return 0
    return max(0, int((expira - datetime.utcnow()).total_seconds()))


def dias_trial_restantes(usuario):
    """Retorna quantos dias inteiros ainda restam do trial."""
    if not usuario or not usuario["trial_ends_at"]:
        return 0
    try:
        trial_ends = datetime.fromisoformat(usuario["trial_ends_at"])
    except ValueError:
        return 0
    segundos = int((trial_ends - datetime.utcnow()).total_seconds())
    return max(0, (segundos // 86400) + 1)


def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


def acesso_requerido(f):
    """
    Libera visitante por 10 minutos, usuario em trial e usuario ativo.
    Bloqueia visitante vencido e usuario com trial expirado.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        usuario = usuario_atual()
        if usuario:
            if status_plano_usuario(usuario) == "expired":
                return redirect(url_for("pagamento"))
            return f(*args, **kwargs)

        if segundos_demo_restantes() <= 0:
            flash(
                "Sua degustacao de 10 minutos terminou. Crie sua conta para liberar 7 dias gratis.",
                "erro",
            )
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        usuario = usuario_atual()
        if usuario and status_plano_usuario(usuario) == "expired":
            return redirect(url_for("pagamento"))
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "").strip()
        usuario = buscar_usuario_por_email(email)

        if usuario and usuario["senha_hash"] == senha:
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            session["nome_comercio"] = usuario["nome_comercio"]
            registrar_login(usuario["id"])
            notificar_login_admin(usuario, metodo="email_senha")

            if status_plano_usuario(usuario) == "expired":
                return redirect(url_for("pagamento"))
            return redirect(url_for("dashboard"))

        flash("E-mail ou senha incorretos.", "erro")

    iniciar_demo_se_preciso()
    return render_template(
        "login.html",
        demo_seconds_remaining=segundos_demo_restantes(),
        checkout_url=MERCADO_PAGO_CHECKOUT_URL,
    )


@app.route("/registrar", methods=["POST"])
def registrar():
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "").strip()
    nome_comercio = request.form.get("nome_comercio", "").strip() or "Meu Comercio"

    if not all([nome, email, senha]):
        flash("Preencha nome, e-mail e senha para criar sua conta.", "erro")
        return redirect(url_for("login"))

    if buscar_usuario_por_email(email):
        flash("Este e-mail ja tem conta. Entre com sua senha.", "erro")
        return redirect(url_for("login"))

    usuario = criar_usuario_trial(nome, email, senha, nome_comercio)
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario["id"]
    session["usuario_nome"] = usuario["nome"]
    session["nome_comercio"] = usuario["nome_comercio"]
    registrar_login(usuario["id"])
    notificar_login_admin(usuario, metodo="cadastro_trial")
    flash("Conta criada! Seu teste gratis de 7 dias comecou agora.", "sucesso")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET", "POST"])
@acesso_requerido
def dashboard():
    usuario = usuario_atual()
    usuario_id = usuario["id"] if usuario else DEMO_USER_ID
    mensagem_padrao = (
        "Ola {Nome}, faz {Dias} dias que voce veio fazer {Servico} aqui conosco! "
        "Que tal agendarmos o seu proximo horario? Estamos te esperando!"
    )

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        celular = request.form.get("celular", "").strip()
        servico = request.form.get("servico", "").strip()
        data_str = request.form.get("data_servico", "")
        intervalo = int(request.form.get("intervalo", 30))
        mensagem = request.form.get("mensagem", mensagem_padrao).strip()

        if not all([nome, celular, servico, data_str]):
            flash("Preencha todos os campos obrigatorios.", "erro")
            return redirect(url_for("dashboard"))

        data_servico = datetime.strptime(data_str, "%Y-%m-%d").date()
        data_envio = data_servico + timedelta(days=intervalo)
        mensagem_final = (
            mensagem
            .replace("{Nome}", nome)
            .replace("{Dias}", str(intervalo))
            .replace("{Servico}", servico)
        )

        criar_cliente_e_agendamento(
            usuario_id=usuario_id,
            nome=nome,
            celular=celular,
            tipo_servico=servico,
            data_servico=data_str,
            intervalo_dias=intervalo,
            mensagem=mensagem_final,
            data_envio=str(data_envio),
        )

        flash(f"Lembrete agendado para {data_envio.strftime('%d/%m/%Y')}!", "sucesso")
        return redirect(url_for("dashboard"))

    agendamentos = listar_agendamentos(usuario_id)
    garantir_horarios_padrao(usuario_id)
    horarios_livres = listar_horarios_livres(usuario_id, limite=10)
    agendamentos_site = listar_agendamentos_clientes(usuario_id)
    historico = listar_historico(usuario_id)
    hoje = datetime.now().strftime("%Y-%m-%d")
    public_agenda_url = url_for("agenda_publica", usuario_id=usuario_id, _external=True)
    whatsapp_profissional = usuario["whatsapp_profissional"] if usuario else ""
    slug_link = usuario["slug_link"] if usuario else ""
    link_profissional_curto = ""
    if slug_link:
        link_profissional_curto = url_for("link_profissional", slug=slug_link, _external=True)
    msg_instagram = (
        f"Ola, me chamo {{Nome}} e vim pelo Instagram. "
        f"Quero ver os horarios disponiveis da {session.get('nome_comercio', 'manicure')}: {public_agenda_url}"
    )
    whatsapp_link_profissional = ""
    if whatsapp_profissional:
        numero = "".join(ch for ch in whatsapp_profissional if ch.isdigit())
        whatsapp_link_profissional = f"https://wa.me/55{numero}?text={quote_plus(msg_instagram)}"
    conversas_ia = listar_conversas_ia(usuario_id) if usuario else []

    return render_template(
        "dashboard.html",
        agendamentos=agendamentos,
        hoje=hoje,
        mensagem_padrao=mensagem_padrao,
        nome_comercio=session.get("nome_comercio", "Degustacao VoltaCliente"),
        is_demo=usuario is None,
        demo_seconds_remaining=segundos_demo_restantes() if usuario is None else 0,
        plan_status=status_plano_usuario(usuario),
        trial_days_remaining=dias_trial_restantes(usuario),
        checkout_url=MERCADO_PAGO_CHECKOUT_URL,
        public_agenda_url=public_agenda_url,
        horarios_livres=horarios_livres,
        agendamentos_site=agendamentos_site,
        historico=historico,
        whatsapp_profissional=whatsapp_profissional,
        whatsapp_link_profissional=whatsapp_link_profissional,
        msg_instagram=msg_instagram,
        slug_link=slug_link,
        link_profissional_curto=link_profissional_curto,
        conversas_ia=conversas_ia,
    )


@app.route("/configuracao/whatsapp", methods=["POST"])
@acesso_requerido
def configurar_whatsapp():
    usuario = usuario_atual()
    if not usuario:
        flash("Crie sua conta para salvar o WhatsApp profissional.", "erro")
        return redirect(url_for("login"))
    whatsapp = request.form.get("whatsapp_profissional", "").strip()
    atualizar_whatsapp_profissional(usuario["id"], whatsapp)
    flash("WhatsApp profissional salvo.", "sucesso")
    return redirect(url_for("dashboard") + "#link-profissional")


@app.route("/l/<slug>")
def link_profissional(slug):
    """
    Redirecionamento do link profissional curto.
    Ex: voltaclienteconchal.onrender.com/l/bfw0d2
    Redireciona para o WhatsApp do estabelecimento com mensagem de boas-vindas.
    """
    usuario = buscar_usuario_por_slug(slug)
    if not usuario or not usuario["whatsapp_profissional"]:
        return render_template("404.html"), 404

    numero = "".join(ch for ch in usuario["whatsapp_profissional"] if ch.isdigit())
    nome_comercio = usuario["nome_comercio"] or "nosso estabelecimento"
    agenda_url = url_for("agenda_publica", usuario_id=usuario["id"], _external=True)
    mensagem = (
        f"Olá! Vim pelo link do {nome_comercio} e gostaria de saber sobre os horários disponíveis. "
        f"Veja minha agenda aqui: {agenda_url}"
    )
    wpp_url = f"https://wa.me/55{numero}?text={quote_plus(mensagem)}"
    return redirect(wpp_url)


@app.route("/webhook/whatsapp", methods=["POST"])
def webhook_whatsapp():
    """
    Endpoint de Webhook para APIs de WhatsApp (Evolution API, Z-API, etc.).

    Formato esperado (JSON):
    {
        "usuario_id": 1,          # ID do estabelecimento no VoltaCliente
        "remetente": "5519999...", # Numero que enviou a mensagem
        "mensagem": "texto...",
        "de_estabelecimento": false  # true se foi o lojista quem enviou
    }
    """
    data = request.get_json(silent=True) or {}
    usuario_id = data.get("usuario_id")
    remetente = data.get("remetente", "").strip()
    mensagem = data.get("mensagem", "").strip()
    de_estabelecimento = data.get("de_estabelecimento", False)

    if not usuario_id or not remetente or not mensagem:
        return jsonify({"erro": "Dados insuficientes"}), 400

    usuario = buscar_usuario_por_id(usuario_id)
    if not usuario:
        return jsonify({"erro": "Estabelecimento nao encontrado"}), 404

    # Se o próprio lojista enviou mensagem → pausa a IA nessa conversa
    if de_estabelecimento:
        atualizar_estado_conversa(
            usuario_id, remetente, status="pausada", ultima_mensagem=mensagem
        )
        print(f"[IA] Conversa com {remetente} pausada (lojista respondeu).")
        return jsonify({"status": "ia_pausada"})

    # Se foi o cliente enviando → verifica se a IA está ativa ou pode reativar
    conversa = buscar_estado_conversa(usuario_id, remetente)

    if conversa and conversa["status"] == "pausada":
        # Verifica se já passaram 12 horas desde que o dono pausou a IA
        pausado_em_str = conversa["pausado_em"]
        reativar = False
        if pausado_em_str:
            try:
                pausado_em = datetime.fromisoformat(pausado_em_str)
                horas_passadas = (datetime.utcnow() - pausado_em).total_seconds() / 3600
                if horas_passadas >= 12:
                    reativar = True
                    print(f"[IA] {horas_passadas:.1f}h sem conversa — reativando IA para {remetente}.")
            except ValueError:
                pass

        if not reativar:
            horas_str = ""
            if pausado_em_str:
                try:
                    pausado_em = datetime.fromisoformat(pausado_em_str)
                    restam = 12 - (datetime.utcnow() - pausado_em).total_seconds() / 3600
                    horas_str = f" ({restam:.1f}h restantes para reativar)"
                except ValueError:
                    pass
            print(f"[IA] Conversa com {remetente} pausada{horas_str}. IA não responde.")
            return jsonify({"status": "ia_pausada_sem_resposta"})

    # IA ativa (ou reativação automática após 12h) → gera resposta com Gemini
    nome_comercio = usuario["nome_comercio"] or "estabelecimento"
    resposta_ia = chamar_gemini(mensagem, nome_comercio)

    # Registra o estado como ativa (limpa o pausado_em)
    atualizar_estado_conversa(
        usuario_id, remetente, status="ativa",
        ultima_mensagem=mensagem
    )

    # Retorna a resposta para a API de WhatsApp enviar ao cliente
    return jsonify({
        "status": "ia_respondeu",
        "resposta": resposta_ia,
        "para": remetente,
    })



@app.route("/ia/toggle", methods=["POST"])
@acesso_requerido
def ia_toggle():
    """Ativa ou pausa a IA para uma conversa especifica via painel."""
    usuario = usuario_atual()
    if not usuario:
        return jsonify({"erro": "Login necessario"}), 401
    cliente_numero = request.form.get("cliente_numero", "").strip()
    novo_status = request.form.get("status", "ativa")
    if not cliente_numero or novo_status not in ("ativa", "pausada"):
        flash("Dados inválidos.", "erro")
        return redirect(url_for("dashboard") + "#ia")
    atualizar_estado_conversa(usuario["id"], cliente_numero, status=novo_status)
    flash(f"IA {novo_status} para o número {cliente_numero}.", "sucesso")
    return redirect(url_for("dashboard") + "#ia")


@app.route("/agenda/<int:usuario_id>", methods=["GET", "POST"])
def agenda_publica(usuario_id):
    usuario = buscar_usuario_por_id(usuario_id)
    if not usuario:
        return "Agenda nao encontrada.", 404

    garantir_horarios_padrao(usuario_id)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        celular = request.form.get("celular", "").strip()
        servico = request.form.get("servico", "").strip()
        horario_id = int(request.form.get("horario_id", "0"))

        if not all([nome, celular, horario_id]):
            flash("Preencha nome, WhatsApp e escolha um horario.", "erro")
            return redirect(url_for("agenda_publica", usuario_id=usuario_id))

        agendamento = criar_agendamento_publico(usuario_id, nome, celular, servico, horario_id)
        if not agendamento:
            flash("Esse horario nao esta mais disponivel. Escolha outro.", "erro")
            return redirect(url_for("agenda_publica", usuario_id=usuario_id))

        enviar_email_simples(
            usuario["email"],
            "Novo agendamento pelo VoltaCliente",
            [
                f"Nova cliente: {agendamento['cliente_nome']}",
                f"WhatsApp: {agendamento['cliente_celular']}",
                f"Servico: {agendamento['servico']}",
                f"Data: {agendamento['data']} as {agendamento['hora_inicio']}",
            ],
        )
        flash("Horario marcado com sucesso! O estabelecimento foi avisado.", "sucesso")
        return redirect(url_for("agenda_publica", usuario_id=usuario_id))

    return render_template(
        "agenda_publica.html",
        usuario=usuario,
        horarios=listar_horarios_livres(usuario_id, limite=30),
    )


@app.route("/agendamentos-site/<int:agendamento_id>/cancelar", methods=["POST"])
@acesso_requerido
def cancelar_agendamento_site(agendamento_id):
    usuario = usuario_atual()
    usuario_id = usuario["id"] if usuario else DEMO_USER_ID
    agendamento = cancelar_agendamento_cliente(usuario_id, agendamento_id)
    if agendamento:
        if usuario:
            enviar_email_simples(
                usuario["email"],
                "Agendamento cancelado pelo VoltaCliente",
                [
                    f"Cliente: {agendamento['cliente_nome']}",
                    f"Horario liberado: {agendamento['data']} as {agendamento['hora_inicio']}",
                ],
            )
        flash("Agendamento cancelado e horario liberado.", "sucesso")
    else:
        flash("Nao foi possivel cancelar esse agendamento.", "erro")
    return redirect(url_for("dashboard") + "#historico")


@app.route("/pagamento")
@login_requerido
def pagamento():
    usuario = usuario_atual()
    if usuario and status_plano_usuario(usuario) == "active":
        return redirect(url_for("dashboard"))
    return render_template(
        "pagamento.html",
        checkout_url=MERCADO_PAGO_CHECKOUT_URL,
        valor="R$ 30,00",
    )


@app.route("/api/stats")
@acesso_requerido
def stats():
    usuario = usuario_atual()
    usuario_id = usuario["id"] if usuario else DEMO_USER_ID
    agendamentos = listar_agendamentos(usuario_id)

    return jsonify({
        "total": len(agendamentos),
        "pendentes": sum(1 for a in agendamentos if a["status"] == "pendente"),
        "enviados": sum(1 for a in agendamentos if a["status"] == "enviado"),
    })


@app.route("/static/service-worker.js")
def service_worker():
    from flask import send_from_directory
    return send_from_directory("static", "service-worker.js", mimetype="application/javascript")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Iniciando VoltaCliente Conchal...")
    print(f"Acesse: http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)

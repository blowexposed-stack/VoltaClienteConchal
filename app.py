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
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, session, url_for
)

sys.path.insert(0, os.path.dirname(__file__))
from database.models import (
    buscar_usuario_por_email,
    buscar_usuario_por_id,
    criar_cliente_e_agendamento,
    criar_usuario_trial,
    init_db,
    listar_agendamentos,
    registrar_login,
    status_plano_usuario,
)
from notificacoes import notificar_login_admin


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
    hoje = datetime.now().strftime("%Y-%m-%d")

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
    )


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

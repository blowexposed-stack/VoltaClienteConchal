"""
app.py - Backend principal do Micro-SaaS de Retenção de Clientes via WhatsApp
Framework: Flask | Banco: SQLite | Autenticação: Sessão simples
"""

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from datetime import datetime, timedelta
import sys
import os

# Adiciona o diretório raiz ao path para importar módulos
sys.path.insert(0, os.path.dirname(__file__))
from database.models import (
    init_db, buscar_usuario_por_email,
    criar_cliente_e_agendamento, listar_agendamentos
)

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "sua-chave-secreta-local-troque-em-producao"
)


# ──────────────────────────────────────────────
# Inicialização do banco de dados
# ──────────────────────────────────────────────
with app.app_context():
    init_db()


# ──────────────────────────────────────────────
# Decorador para proteger rotas autenticadas
# ──────────────────────────────────────────────
def login_requerido(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────────
# ROTA: Login
# ──────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "").strip()

        usuario = buscar_usuario_por_email(email)

        # Autenticação simples — em produção use bcrypt para hash de senha!
        if usuario and usuario["senha_hash"] == senha:
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            session["nome_comercio"] = usuario["nome_comercio"]
            return redirect(url_for("dashboard"))
        else:
            flash("E-mail ou senha incorretos. Tente: admin@demo.com / demo123", "erro")

    return render_template("login.html")


# ──────────────────────────────────────────────
# ROTA: Logout
# ──────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ──────────────────────────────────────────────
# ROTA: Dashboard principal (cadastro + listagem)
# ──────────────────────────────────────────────
@app.route("/dashboard", methods=["GET", "POST"])
@login_requerido
def dashboard():
    usuario_id = session["usuario_id"]
    mensagem_padrao = "Olá {Nome}, faz {Dias} dias que você veio fazer {Servico} aqui conosco! 😊 Que tal agendarmos o seu próximo horário? Estamos te esperando!"

    if request.method == "POST":
        nome        = request.form.get("nome", "").strip()
        celular     = request.form.get("celular", "").strip()
        servico     = request.form.get("servico", "").strip()
        data_str    = request.form.get("data_servico", "")
        intervalo   = int(request.form.get("intervalo", 30))
        mensagem    = request.form.get("mensagem", mensagem_padrao).strip()

        # Validações básicas
        if not all([nome, celular, servico, data_str]):
            flash("Preencha todos os campos obrigatórios.", "erro")
            return redirect(url_for("dashboard"))

        # Calcula a data de envio
        data_servico = datetime.strptime(data_str, "%Y-%m-%d").date()
        data_envio   = data_servico + timedelta(days=intervalo)

        # Substitui as variáveis da mensagem pelos valores reais
        mensagem_final = (
            mensagem
            .replace("{Nome}", nome)
            .replace("{Dias}", str(intervalo))
            .replace("{Servico}", servico)
        )

        # Salva no banco de dados
        criar_cliente_e_agendamento(
            usuario_id=usuario_id,
            nome=nome,
            celular=celular,
            tipo_servico=servico,
            data_servico=data_str,
            intervalo_dias=intervalo,
            mensagem=mensagem_final,
            data_envio=str(data_envio)
        )

        flash(f"✅ Lembrete agendado para {data_envio.strftime('%d/%m/%Y')}!", "sucesso")
        return redirect(url_for("dashboard"))

    # Carrega a lista de agendamentos para exibição
    agendamentos = listar_agendamentos(usuario_id)
    hoje = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "dashboard.html",
        agendamentos=agendamentos,
        hoje=hoje,
        mensagem_padrao=mensagem_padrao,
        nome_comercio=session.get("nome_comercio", "Meu Comércio")
    )


# ──────────────────────────────────────────────
# ROTA: API para estatísticas (mini dashboard)
# ──────────────────────────────────────────────
@app.route("/api/stats")
@login_requerido
def stats():
    usuario_id = session["usuario_id"]
    agendamentos = listar_agendamentos(usuario_id)

    total     = len(agendamentos)
    pendentes = sum(1 for a in agendamentos if a["status"] == "pendente")
    enviados  = sum(1 for a in agendamentos if a["status"] == "enviado")

    return jsonify({
        "total": total,
        "pendentes": pendentes,
        "enviados": enviados
    })


# ──────────────────────────────────────────────
# Rota para servir o service worker na raiz (necessário para PWA)
@app.route("/static/service-worker.js")
def service_worker():
    from flask import send_from_directory
    return send_from_directory("static", "service-worker.js",
                               mimetype="application/javascript")


# Ponto de entrada
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Iniciando Micro-SaaS de Retenção de Clientes...")
    port = int(os.environ.get("PORT", 5000))
    print(f"📱 Acesse: http://localhost:{port}")
    print("🔑 Login demo: admin@demo.com / demo123")
    app.run(debug=False, host="0.0.0.0", port=port)

import os
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from dotenv import load_dotenv
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False

# ============== BANCO DE DADOS ==============
DATABASE = '/tmp/retencao.db'

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout = 30000;')
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nome TEXT,
            nome_estabelecimento TEXT,
            tipo_negocio TEXT DEFAULT 'barbearia',
            trial_expiry TEXT,
            status TEXT DEFAULT 'trial',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            email TEXT,
            tipo_servico TEXT,
            intervalo_retorno INTEGER DEFAULT 30,
            data_ultimo_servico TEXT,
            data_proximo_contato TEXT,
            status TEXT DEFAULT 'ativo',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        
        CREATE TABLE IF NOT EXISTS servicos (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            intervalo_padrao INTEGER DEFAULT 30,
            descricao TEXT,
            ativo BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        
        CREATE TABLE IF NOT EXISTS fila_envios (
            id INTEGER PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            tipo_mensagem TEXT,
            data_envio_agendada TEXT,
            data_envio_real TEXT,
            status TEXT DEFAULT 'pendente',
            tentativas INTEGER DEFAULT 0,
            resposta_api TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS demo_sessions (
            ip TEXT PRIMARY KEY,
            inicio TEXT NOT NULL,
            tempo_iniciar TEXT NOT NULL
        );
    ''')
    db.commit()
    db.close()

# Inicializa o banco imediatamente
init_db()

# ============== FUNÇÃO AUXILIAR SALVAR CLIENTE ==============
def salvar_cliente_db(user_id, form):
    nome = form.get('nome')
    whatsapp = form.get('whatsapp')
    email = form.get('email', '')
    
    tipo_servico = form.get('tipo_servico') or form.get('servico') or form.get('servico_realizado', '')
    intervalo_retorno_raw = form.get('intervalo_retorno')
    data_proximo_contato = form.get('data_proximo_contato') or form.get('data_lembrete') or form.get('enviar_lembrete')
    mensagem_personalizada = form.get('mensagem') or form.get('mensagem_personalizada', '')
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    if intervalo_retorno_raw:
        intervalo_retorno = int(intervalo_retorno_raw)
        data_proximo = (datetime.now() + timedelta(days=intervalo_retorno)).strftime('%Y-%m-%d')
    elif data_proximo_contato:
        data_proximo = data_proximo_contato
        if '/' in data_proximo:
            try:
                data_proximo = datetime.strptime(data_proximo, '%d/%m/%Y').strftime('%Y-%m-%d')
            except:
                pass
        intervalo_retorno = 30
    else:
        intervalo_retorno = 30
        data_proximo = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        
    db = get_db()
    db.execute('''
        INSERT INTO clientes (user_id, nome, whatsapp, email, tipo_servico, intervalo_retorno, data_ultimo_servico, data_proximo_contato, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ativo')
    ''', (user_id, nome, whatsapp, email, tipo_servico, intervalo_retorno, hoje, data_proximo))
    db.commit()
    db.close()

# ============== ROTAS DE AUTENTICAÇÃO ==============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def check_demo_time(f):
    """Verifica se o tempo de demo expirou"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'demo_mode' in session:
            inicio = datetime.fromisoformat(session.get('demo_inicio', datetime.now().isoformat()))
            if datetime.now() > inicio + timedelta(minutes=10):
                session.clear()
                flash('⏱️ Seu tempo de demonstração de 10 minutos expirou! Crie uma conta para continuar.', 'info')
                return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if 'demo_mode' in session:
        # Verifica se demo ainda está válida
        inicio = datetime.fromisoformat(session.get('demo_inicio', datetime.now().isoformat()))
        if datetime.now() > inicio + timedelta(minutes=10):
            session.clear()
            flash('⏱️ Seu tempo de demonstração de 10 minutos expirou! Crie uma conta para continuar.', 'info')
        else:
            return redirect(url_for('dashboard_demo'))
    return render_template('login.html')

@app.route('/registrar', methods=['POST'])
def registrar():
    try:
        email = request.form.get('email')
        senha = request.form.get('senha') or request.form.get('password')
        nome = request.form.get('nome', 'Usuário')
        nome_estabelecimento = request.form.get('nome_estabelecimento', 'Meu Estabelecimento')
        tipo_negocio = request.form.get('tipo_negocio', 'barbearia')
        
        if not email or not senha:
            flash('❌ E-mail e senha são obrigatórios.', 'erro')
            return redirect(url_for('index'))
            
        db = get_db()
        trial_expiry = (datetime.now() + timedelta(days=7)).isoformat()
        
        db.execute('''
            INSERT OR REPLACE INTO users (email, password, nome, nome_estabelecimento, tipo_negocio, trial_expiry)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, senha, nome, nome_estabelecimento, tipo_negocio, trial_expiry))
        db.commit()
        
        user = db.execute('SELECT id, email FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['email'] = user['email']
        session.pop('demo_mode', None)  # Remove demo mode se estava ativo
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'❌ Erro ao registrar: {str(e)}', 'erro')
        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    try:
        email = request.form.get('email')
        senha = request.form.get('senha') or request.form.get('password')
        
        db = get_db()
        user = db.execute('SELECT id, email, password FROM users WHERE email = ?', (email,)).fetchone()
        
        if user and str(user['password']) == str(senha):
            session['user_id'] = user['id']
            session['email'] = user['email']
            session.pop('demo_mode', None)  # Remove demo mode se estava ativo
            return redirect(url_for('dashboard'))
        else:
            flash('❌ E-mail ou senha inválidos', 'erro')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'❌ Erro interno: {str(e)}', 'erro')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ============== DEMO MODE ==============
@app.route('/demo')
def start_demo():
    """Inicia o modo de demonstração de 10 minutos"""
    session['demo_mode'] = True
    session['demo_inicio'] = datetime.now().isoformat()
    return redirect(url_for('dashboard_demo'))

# ============== DASHBOARD & OUTRAS ROTAS ==============
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    db = get_db()
    if request.method == 'POST':
        salvar_cliente_db(session['user_id'], request.form)
        return redirect(url_for('dashboard'))
        
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    clientes = db.execute('SELECT * FROM clientes WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    
    context = {
        'user': dict(user) if user else {},
        'clientes': clientes,
        'clientes_semana': [],
        'total_clientes': len(clientes),
        'fila_pendente': 0
    }
    return render_template('dashboard.html', **context)

# ============== ROTAS DE DEMO ==============
@app.route('/dashboard_demo')
@app.route('/dashboard-demo')
@check_demo_time
def dashboard_demo():
    """Página de demonstração com timer de 10 minutos"""
    if 'demo_mode' not in session:
        return redirect(url_for('start_demo'))
    
    # Calcula tempo restante
    inicio = datetime.fromisoformat(session.get('demo_inicio', datetime.now().isoformat()))
    tempo_decorrido = (datetime.now() - inicio).total_seconds()
    tempo_restante = max(0, 600 - tempo_decorrido)  # 600 segundos = 10 minutos
    
    if tempo_restante <= 0:
        session.clear()
        flash('⏱️ Seu tempo de demonstração expirou! Crie uma conta para continuar.', 'info')
        return redirect(url_for('index'))
    
    context = {
        'tempo_restante': int(tempo_restante),
        'total_clientes': 18,
        'fila_pendente': 5,
        'clientes_semana': []
    }
    return render_template('dashboard_demo.html', **context)

@app.route('/cliente/novo')
@check_demo_time
def novo_cliente():
    """Rota para adicionar novo cliente (demo)"""
    if 'demo_mode' not in session:
        return redirect(url_for('start_demo'))
    flash('📌 Na demo não é possível adicionar clientes. Crie uma conta para começar!', 'info')
    return redirect(url_for('dashboard_demo'))

@app.route('/dashboard/agendar/<slug>')
def agenda_publica(slug):
    db = get_db()
    user = db.execute('SELECT * FROM users LIMIT 1').fetchone()
    if not user:
        user = {'id': 1, 'nome_estabelecimento': 'VoltaCliente Conchal', 'tipo_negocio': 'Geral'}
    return render_template('agenda_publica.html', user=user, servicos=[])

@app.errorhandler(404)
def not_found(error):
    """Trata rotas 404 - redireciona para página apropriada"""
    if 'demo_mode' in session:
        return redirect(url_for('dashboard_demo')), 302
    elif 'user_id' in session:
        return redirect(url_for('dashboard')), 302
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

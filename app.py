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
# Alterado para a pasta /tmp para evitar erros de permissão no Render
DATABASE = '/tmp/retencao.db'

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    # Aumenta o timeout para evitar travamentos de concorrência no SQLite
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
        
        CREATE TABLE IF NOT EXISTS historico_contatos (
            id INTEGER PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            tipo TEXT,
            descricao TEXT,
            data_contato TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );
    ''')
    db.commit()
    db.close()

# Garante que o banco seja inicializado ao rodar via Gunicorn no Render
init_db()

# ============== AGENDADOR DE TAREFAS AUTOMÁTICO ==============
scheduler = BackgroundScheduler()

def processar_fila_diaria():
    """Tarefa que roda diariamente para processar lembretes e renovar ciclos automaticamente"""
    db = get_db()
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Encontrar clientes que precisam de contato hoje
    clientes_para_contatar = db.execute('''
        SELECT c.*, u.nome_estabelecimento, u.email 
        FROM clientes c
        JOIN users u ON c.user_id = u.id
        WHERE c.data_proximo_contato = ? AND c.status = 'ativo'
    ''', (hoje,)).fetchall()
    
    for cliente in clientes_para_contatar:
        # 1. Criar entrada na fila de envios para a API disparar
        db.execute('''
            INSERT INTO fila_envios (cliente_id, user_id, tipo_mensagem, data_envio_agendada, status)
            VALUES (?, ?, 'lembrete_retorno', ?, 'pendente')
        ''', (cliente['id'], cliente['user_id'], hoje))
        
        # 2. RENOVAÇÃO DO CICLO: Calcula a data do próximo lembrete com base no intervalo do cliente
        intervalo = cliente['intervalo_retorno'] if cliente['intervalo_retorno'] else 30
        nova_data_contato = (datetime.now() + timedelta(days=intervalo)).strftime('%Y-%m-%d')
        
        # 3. Atualiza o cadastro para o próximo período sem intervenção humana
        db.execute('''
            UPDATE clientes 
            SET data_ultimo_servico = ?, data_proximo_contato = ?
            WHERE id = ?
        ''', (hoje, nova_data_contato, cliente['id']))
        
        # 4. Registra no histórico que um lembrete foi agendado ciclicamente
        db.execute('''
            INSERT INTO historico_contatos (cliente_id, tipo, descricao)
            VALUES (?, 'sistema', ?)
        ''', (cliente['id'], f'Lembrete enviado. Próximo ciclo automatizado para: {nova_data_contato}'))
    
    db.commit()
    db.close()
    print(f"[{hoje}] {len(clientes_para_contatar)} clientes adicionados à fila e reagendados para o próximo ciclo.")

if not scheduler.running:
    scheduler.add_job(func=processar_fila_diaria, trigger="cron", hour=8, minute=0)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

# ============== AUTH ==============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    context = {
        'demo_seconds_remaining': 600,
        'checkout_url': os.getenv('MP_CHECKOUT_URL', '#')
    }
    return render_template('login.html', **context)

@app.route('/registrar', methods=['POST'])
def registrar():
    try:
        email = request.form.get('email')
        senha = request.form.get('senha')
        nome = request.form.get('nome')
        nome_estabelecimento = request.form.get('nome_estabelecimento')
        tipo_negocio = request.form.get('tipo_negocio', 'barbearia')
        
        db = get_db()
        trial_expiry = (datetime.now() + timedelta(days=7)).isoformat()
        
        db.execute('''
            INSERT INTO users (email, password, nome, nome_estabelecimento, tipo_negocio, trial_expiry)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (email, senha, nome, nome_estabelecimento, tipo_negocio, trial_expiry))
        db.commit()
        
        user = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['email'] = email
        
        flash('✅ Conta criada! Você tem 7 dias de trial grátis', 'sucesso')
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'❌ Erro: {str(e)}', 'erro')
        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    try:
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        db = get_db()
        user = db.execute(
            'SELECT id, email, password FROM users WHERE email = ?', 
            (email,)
        ).fetchone()
        
        if user and user['password'] == senha:
            session['user_id'] = user['id']
            session['email'] = user['email']
            return redirect(url_for('dashboard'))
        else:
            flash('❌ E-mail ou senha inválidos', 'erro')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'❌ Erro: {str(e)}', 'erro')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ============== DASHBOARD ==============
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE id = ?', 
        (session['user_id'],)
    ).fetchone()
    
    # Clientes que devem retornar essa semana
    hoje = datetime.now().strftime('%Y-%m-%d')
    proxima_semana = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    
    clientes_semana = db.execute('''
        SELECT * FROM clientes 
        WHERE user_id = ? AND data_proximo_contato BETWEEN ? AND ? AND status = 'ativo'
        ORDER BY data_proximo_contato ASC
    ''', (session['user_id'], hoje, proxima_semana)).fetchall()
    
    total_clientes = db.execute(
        'SELECT COUNT(*) as total FROM clientes WHERE user_id = ? AND status = "ativo"',
        (session['user_id'],)
    ).fetchone()['total']
    
    fila_pendente = db.execute(
        'SELECT COUNT(*) as total FROM fila_envios WHERE user_id = ? AND status = "pendente"',
        (session['user_id'],)
    ).fetchone()['total']
    
    context = {
        'user': dict(user),
        'clientes_semana': clientes_semana,
        'total_clientes': total_clientes,
        'fila_pendente': fila_pendente,
    }
    return render_template('dashboard.html', **context)

# ============== GESTÃO DE CLIENTES ==============
@app.route('/clientes')
@login_required
def listar_clientes():
    db = get_db()
    clientes = db.execute('''
        SELECT * FROM clientes WHERE user_id = ? ORDER BY data_proximo_contato ASC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('clientes.html', clientes=clientes)

@app.route('/cliente/novo', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    db = get_db()
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        whatsapp = request.form.get('whatsapp')
        email = request.form.get('email')
        tipo_servico = request.form.get('tipo_servico')
        intervalo_retorno = int(request.form.get('intervalo_retorno', 30))
        
        data_ultimo_servico = datetime.now().strftime('%Y-%m-%d')
        data_proximo_contato = (datetime.now() + timedelta(days=intervalo_retorno)).strftime('%Y-%m-%d')
        
        db.execute('''
            INSERT INTO clientes (user_id, nome, whatsapp, email, tipo_servico, intervalo_retorno, data_ultimo_servico, data_proximo_contato)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], nome, whatsapp, email, tipo_servico, intervalo_retorno, data_ultimo_servico, data_proximo_contato))
        
        db.commit()
        flash(f'✅ Cliente {nome} cadastrado! Próximo contato: {data_proximo_contato}', 'sucesso')
        return redirect(url_for('listar_clientes'))
    
    servicos = db.execute(
        'SELECT * FROM servicos WHERE user_id = ? AND ativo = 1',
        (session['user_id'],)
    ).fetchall()
    
    return render_template('novo_cliente.html', servicos=servicos)

@app.route('/cliente/<int:cliente_id>/registrar-servico', methods=['POST'])
@login_required
def registrar_servico(cliente_id):
    """Registra que o cliente fez um serviço e recalcula próximo contato"""
    db = get_db()
    
    cliente = db.execute(
        'SELECT * FROM clientes WHERE id = ? AND user_id = ?',
        (cliente_id, session['user_id'])
    ).fetchone()
    
    if not cliente:
        return jsonify({'error': 'Cliente não encontrado'}), 404
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    proximo_contato = (datetime.now() + timedelta(days=cliente['intervalo_retorno'])).strftime('%Y-%m-%d')
    
    db.execute('''
        UPDATE clientes SET data_ultimo_servico = ?, data_proximo_contato = ?
        WHERE id = ?
    ''', (hoje, proximo_contato, cliente_id))
    
    db.execute('''
        INSERT INTO historico_contatos (cliente_id, tipo, descricao)
        VALUES (?, 'servico', ?)
    ''', (cliente_id, f'Serviço registrado: {request.form.get("descricao", "Serviço")}'))
    
    db.commit()
    flash(f'✅ Serviço registrado! Próximo contato: {proximo_contato}', 'sucesso')
    return redirect(url_for('listar_clientes'))

# ============== GESTÃO DE SERVIÇOS ==============
@app.route('/servicos')
@login_required
def listar_servicos():
    db = get_db()
    servicos = db.execute(
        'SELECT * FROM servicos WHERE user_id = ? ORDER BY nome',
        (session['user_id'],)
    ).fetchall()
    
    return render_template('servicos.html', servicos=servicos)

@app.route('/servico/novo', methods=['POST'])
@login_required
def novo_servico():
    nome = request.form.get('nome')
    intervalo_padrao = int(request.form.get('intervalo_padrao', 30))
    descricao = request.form.get('descricao')
    
    db = get_db()
    db.execute('''
        INSERT INTO servicos (user_id, nome, intervalo_padrao, descricao)
        VALUES (?, ?, ?, ?)
    ''', (session['user_id'], nome, intervalo_padrao, descricao))
    db.commit()
    
    flash(f'✅ Serviço "{nome}" criado com intervalo padrão de {intervalo_padrao} dias', 'sucesso')
    return redirect(url_for('listar_servicos'))

# ============== GESTÃO DE FILA ==============
@app.route('/fila')
@login_required
def fila_envios():
    db = get_db()
    fila = db.execute('''
        SELECT f.*, c.nome, c.whatsapp 
        FROM fila_envios f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.user_id = ?
        ORDER BY f.data_envio_agendada ASC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('fila.html', fila=fila)

@app.route('/api/fila/<int:fila_id>/processar', methods=['POST'])
@login_required
def processar_fila_item(fila_id):
    """Simula envio para Evolution API"""
    db = get_db()
    
    item = db.execute(
        'SELECT * FROM fila_envios WHERE id = ? AND user_id = ?',
        (fila_id, session['user_id'])
    ).fetchone()
    
    if not item:
        return jsonify({'error': 'Item não encontrado'}), 404
    
    db.execute('''
        UPDATE fila_envios SET status = 'enviado', data_envio_real = ?, resposta_api = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), 'Enviado (mock)', fila_id))
    
    db.commit()
    return jsonify({'status': 'success', 'message': 'Mensagem enviada'})

# ============== CONFIGURAÇÕES ==============
@app.route('/configuracoes')
@login_required
def configuracoes():
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()
    
    tipos_negocio = ['Barbearia', 'Manicure', 'Estética', 'Pet Shop', 'Salão', 'Consultório', 'Outro']
    return render_template('configuracoes.html', user=dict(user), tipos_negocio=tipos_negocio)

@app.route('/configuracoes/atualizar', methods=['POST'])
@login_required
def atualizar_configuracoes():
    nome_estabelecimento = request.form.get('nome_estabelecimento')
    tipo_negocio = request.form.get('tipo_negocio')
    
    db = get_db()
    db.execute('''
        UPDATE users SET nome_estabelecimento = ?, tipo_negocio = ?
        WHERE id = ?
    ''', (nome_estabelecimento, tipo_negocio, session['user_id']))
    db.commit()
    
    flash('✅ Configurações updated com sucesso', 'sucesso')
    return redirect(url_for('configuracoes'))

# ============== HEALTH CHECK ==============
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

# ============== ERRO 404 ==============
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

# ============== INICIALIZAR ==============
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

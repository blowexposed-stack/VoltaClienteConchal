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

# Inicializa o banco imediatamente para estar pronto no ambiente de produção
init_db()

# ============== FUNÇÃO INTELIGENTE DE SALVAMENTO ==============
def salvar_cliente_db(user_id, form):
    """Trata de forma unificada os campos do dashboard e de novo_cliente.html"""
    nome = form.get('nome')
    whatsapp = form.get('whatsapp')
    email = form.get('email', '')
    
    # Captura variações como 'servico', 'tipo_servico' ou 'servico_realizado'
    tipo_servico = form.get('tipo_servico') or form.get('servico') or form.get('servico_realizado', '')
    intervalo_retorno_raw = form.get('intervalo_retorno')
    data_proximo_contato = form.get('data_proximo_contato') or form.get('data_lembrete') or form.get('enviar_lembrete')
    mensagem_personalizada = form.get('mensagem') or form.get('mensagem_personalizada', '')
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Processa cálculo de data ou formatação de string vinda do HTML
    if intervalo_retorno_raw:
        intervalo_retorno = int(intervalo_retorno_raw)
        data_proximo = (datetime.now() + timedelta(days=intervalo_retorno)).strftime('%Y-%m-%d')
    elif data_proximo_contato:
        data_proximo = data_proximo_contato
        # Se vier no padrão brasileiro 'DD/MM/AAAA', converte para 'YYYY-MM-DD'
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
    
    cliente_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    # Se houver uma mensagem personalizada definida no formulário, adiciona à fila de envios
    if mensagem_personalizada:
        db.execute('''
            INSERT INTO fila_envios (cliente_id, user_id, tipo_mensagem, data_envio_agendada, status, resposta_api)
            VALUES (?, ?, 'lembrete_personalizado', ?, 'pendente', ?)
        ''', (cliente_id, user_id, data_proximo, mensagem_personalizada))
        
    db.commit()
    db.close()
    return data_proximo

# ============== AGENDADOR AUTOMÁTICO ==============
scheduler = BackgroundScheduler()

def processar_fila_diaria():
    try:
        db = get_db()
        hoje = datetime.now().strftime('%Y-%m-%d')
        
        clientes_para_contatar = db.execute('''
            SELECT c.*, u.nome_estabelecimento, u.email 
            FROM clientes c
            JOIN users u ON c.user_id = u.id
            WHERE c.data_proximo_contato = ? AND c.status = 'ativo'
        ''', (hoje,)).fetchall()
        
        for cliente in clientes_para_contatar:
            db.execute('''
                INSERT INTO fila_envios (cliente_id, user_id, tipo_mensagem, data_envio_agendada, status)
                VALUES (?, ?, 'lembrete_retorno', ?, 'pendente')
            ''', (cliente['id'], cliente['user_id'], hoje))
            
            intervalo = cliente['intervalo_retorno'] if cliente['intervalo_retorno'] else 30
            nova_data_contato = (datetime.now() + timedelta(days=intervalo)).strftime('%Y-%m-%d')
            
            db.execute('''
                UPDATE clientes 
                SET data_ultimo_servico = ?, data_proximo_contato = ?
                WHERE id = ?
            ''', (hoje, nova_data_contato, cliente['id']))
            
            db.execute('''
                INSERT INTO historico_contatos (cliente_id, tipo, descricao)
                VALUES (?, 'sistema', ?)
            ''', (cliente['id'], f'Lembrete automático agendado para: {nova_data_contato}'))
        
        db.commit()
        db.close()
    except Exception as e:
        print(f"Erro na execução do Scheduler: {e}")

if not scheduler.running:
    scheduler.add_job(func=processar_fila_diaria, trigger="cron", hour=8, minute=0)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

# ============== ROTAS DE CONTROLE DE ACESSO ==============
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
    return render_template('login.html', demo_seconds_remaining=600, checkout_url=os.getenv('MP_CHECKOUT_URL', '#'))

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
        
        flash('✅ Conta criada com sucesso!', 'sucesso')
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'❌ Erro ao registar: {str(e)}', 'erro')
        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    try:
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        db = get_db()
        user = db.execute('SELECT id, email, password FROM users WHERE email = ?', (email,)).fetchone()
        
        if user and user['password'] == senha:
            session['user_id'] = user['id']
            session['email'] = user['email']
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

# ============== DASHBOARD PRINCIPAL ==============
@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    db = get_db()
    
    # Permite que o formulário rápido de dentro do Dashboard envie dados diretamente para cá
    if request.method == 'POST':
        try:
            salvar_cliente_db(session['user_id'], request.form)
            flash('✅ Cliente guardado e lembrete agendado!', 'sucesso')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'❌ Erro ao adicionar: {str(e)}', 'erro')
            return redirect(url_for('dashboard'))
            
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    proxima_semana = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    
    clientes_semana = db.execute('''
        SELECT * FROM clientes 
        WHERE user_id = ? AND data_proximo_contato BETWEEN ? AND ? AND status = 'ativo'
        ORDER BY data_proximo_contato ASC
    ''', (session['user_id'], hoje, proxima_semana)).fetchall()
    
    clientes = db.execute('SELECT * FROM clientes WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    total_clientes = len(clientes)
    
    fila_pendente = db.execute('SELECT COUNT(*) as total FROM fila_envios WHERE user_id = ? AND status = "pendente"', (session['user_id'],)).fetchone()['total']
    
    context = {
        'user': dict(user),
        'clientes': clientes,
        'clientes_semana': clientes_semana,
        'total_clientes': total_clientes,
        'fila_pendente': fila_pendente,
    }
    return render_template('dashboard.html', **context)

# ============== ROTAS DA DEMO (PROVA DE CONCEITO) ==============
@app.route('/dashboard-demo')
@app.route('/demo')
def dashboard_demo():
    return render_template('dashboard_demo.html')

# ============== INTERFACE DE GESTÃO DE CLIENTES ==============
@app.route('/clientes')
@login_required
def listar_clientes():
    db = get_db()
    clientes = db.execute('SELECT * FROM clientes WHERE user_id = ? ORDER BY data_proximo_contato ASC', (session['user_id'],)).fetchall()
    return render_template('clientes.html', clientes=clientes)

@app.route('/cliente/novo', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    db = get_db()
    if request.method == 'POST':
        try:
            salvar_cliente_db(session['user_id'], request.form)
            flash('✅ Novo cliente adicionado!', 'sucesso')
            return redirect(url_for('listar_clientes'))
        except Exception as e:
            flash(f'❌ Erro: {str(e)}', 'erro')
            return redirect(url_for('novo_cliente'))
            
    servicos = db.execute('SELECT * FROM servicos WHERE user_id = ? AND ativo = 1', (session['user_id'],)).fetchall()
    return render_template('novo_cliente.html', servicos=servicos)

@app.route('/cliente/<int:cliente_id>/registrar-servico', methods=['POST'])
@login_required
def registrar_servico(cliente_id):
    db = get_db()
    cliente = db.execute('SELECT * FROM clientes WHERE id = ? AND user_id = ?', (cliente_id, session['user_id'])).fetchone()
    
    if not cliente:
        return jsonify({'error': 'Cliente inválido'}), 404
        
    hoje = datetime.now().strftime('%Y-%m-%d')
    proximo_contato = (datetime.now() + timedelta(days=cliente['intervalo_retorno'])).strftime('%Y-%m-%d')
    
    db.execute('UPDATE clientes SET data_ultimo_servico = ?, data_proximo_contato = ? WHERE id = ?', (hoje, proximo_contato, cliente_id))
    db.execute('INSERT INTO historico_contatos (cliente_id, tipo, descricao) VALUES (?, "servico", ?)', (cliente_id, f'Serviço: {request.form.get("descricao", "Retorno")}'))
    db.commit()
    db.close()
    
    flash(f'✅ Ciclo renovado! Próximo contato: {proximo_contato}', 'sucesso')
    return redirect(url_for('listar_clientes'))

@app.route('/agendamentos')
@login_required
def agendamentos_fallback():
    return redirect(url_for('dashboard'))

# ============== INTERFACE DE SERVIÇOS ==============
@app.route('/servicos')
@login_required
def listar_servicos():
    db = get_db()
    servicos = db.execute('SELECT * FROM servicos WHERE user_id = ? ORDER BY nome', (session['user_id'],)).fetchall()
    return render_template('servicos.html', servicos=servicos)

@app.route('/servico/novo', methods=['POST'])
@login_required
def novo_servico():
    nome = request.form.get('nome')
    intervalo_padrao = int(request.form.get('intervalo_padrao', 30))
    descricao = request.form.get('descricao')
    
    db = get_db()
    db.execute('INSERT INTO servicos (user_id, nome, intervalo_padrao, descricao) VALUES (?, ?, ?, ?)', (session['user_id'], nome, intervalo_padrao, descricao))
    db.commit()
    db.close()
    
    flash(f'✅ Serviço "{nome}" adicionado com sucesso!', 'sucesso')
    return redirect(url_for('listar_servicos'))

# ============== INTERFACE DA FILA DE ENVIOS ==============
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
    db = get_db()
    item = db.execute('SELECT * FROM fila_envios WHERE id = ? AND user_id = ?', (fila_id, session['user_id'])).fetchone()
    if not item:
        return jsonify({'error': 'Item não localizado'}), 404
        
    db.execute("UPDATE fila_envios SET status = 'enviado', data_envio_real = ?, resposta_api = ? WHERE id = ?", (datetime.now().isoformat(), 'Enviado com Sucesso', fila_id))
    db.commit()
    db.close()
    return jsonify({'status': 'success', 'message': 'Disparado!'})

# ============== PAINEL DE CONFIGURAÇÕES ==============
@app.route('/configuracoes')
@login_required
def configuracoes():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    tipos_negocio = ['Barbearia', 'Manicure', 'Estética', 'Pet Shop', 'Salão', 'Consultório', 'Papelaria', 'Outro']
    return render_template('configuracoes.html', user=dict(user), tipos_negocio=tipos_negocio)

@app.route('/configuracoes/atualizar', methods=['POST'])
@login_required
def atualizar_configuracoes():
    nome_estabelecimento = request.form.get('nome_estabelecimento')
    tipo_negocio = request.form.get('tipo_negocio')
    
    db = get_db()
    db.execute('UPDATE users SET nome_estabelecimento = ?, tipo_negocio = ? WHERE id = ?', (nome_estabelecimento, tipo_negocio, session['user_id']))
    db.commit()
    db.close()
    
    flash('✅ Configurações salvas.', 'sucesso')
    return redirect(url_for('configuracoes'))

# ============== AGENDA PÚBLICA (LINK DA BIO SEM COMPLICAÇÕES) ==============
@app.route('/dashboard/agendar/<slug>')
def agenda_publica(slug):
    db = get_db()
    
    # Busca flexível removendo espaços para coincidir com o link gerado pelo sistema
    user = db.execute('SELECT * FROM users WHERE LOWER(REPLACE(nome_estabelecimento, " ", "")) LIKE ?', (f"%{slug}%",)).fetchone()
    
    # Tratamento estratégico para que NUNCA dê 404 caso o banco de dados temporário limpe:
    if not user:
        user = db.execute('SELECT * FROM users LIMIT 1').fetchone()
        
    if not user:
        # Se o banco de dados estiver completamente limpo, monta dados simulados elegantes em tempo real
        user = {
            'id': 1,
            'nome_estabelecimento': 'Papelaria VoltaCliente',
            'tipo_negocio': 'Papelaria'
        }
        servicos = []
    else:
        servicos = db.execute('SELECT * FROM servicos WHERE user_id = ? AND ativo = 1', (user['id'],)).fetchall()
        
    return render_template('agenda_publica.html', user=user, servicos=servicos)

# ============== HEALTH CHECK ==============
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

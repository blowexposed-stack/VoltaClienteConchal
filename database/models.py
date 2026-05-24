"""
models.py - Configuração do banco de dados SQLite e definição das tabelas
Usando sqlite3 nativo do Python para manter o projeto leve e sem dependências extras
"""

import sqlite3
import os
from datetime import datetime, timedelta

# Caminho do arquivo do banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), "retencao.db")


def get_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas pelo nome
    return conn


def garantir_coluna(cursor, tabela: str, coluna: str, definicao: str):
    """Adiciona uma coluna se ela ainda nao existir."""
    colunas = [info[1] for info in cursor.execute(f"PRAGMA table_info({tabela})").fetchall()]
    if coluna not in colunas:
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


def init_db():
    """
    Inicializa o banco de dados criando as tabelas se não existirem.
    Chamado uma vez ao iniciar a aplicação.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de usuários (comerciantes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            nome_comercio TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    garantir_coluna(cursor, "usuarios", "trial_started_at", "TIMESTAMP")
    garantir_coluna(cursor, "usuarios", "trial_ends_at", "TIMESTAMP")
    garantir_coluna(cursor, "usuarios", "plan_status", "TEXT DEFAULT 'trial'")
    garantir_coluna(cursor, "usuarios", "mp_preapproval_id", "TEXT")
    garantir_coluna(cursor, "usuarios", "ultimo_login_em", "TIMESTAMP")
    garantir_coluna(cursor, "usuarios", "whatsapp_profissional", "TEXT")

    # Tabela de clientes cadastrados pelo comerciante
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            celular TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # Tabela de agendamentos de lembrete
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            tipo_servico TEXT NOT NULL,
            data_servico DATE NOT NULL,
            intervalo_dias INTEGER NOT NULL,       -- 15, 30 ou 45 dias
            data_envio DATE NOT NULL,              -- data_servico + intervalo_dias
            mensagem_personalizada TEXT NOT NULL,
            status TEXT DEFAULT 'pendente',        -- 'pendente' ou 'enviado'
            enviado_em TIMESTAMP,                  -- data/hora real do envio
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS horarios_disponiveis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            data DATE NOT NULL,
            hora_inicio TEXT NOT NULL,
            hora_fim TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'livre',
            observacao TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            UNIQUE (usuario_id, data, hora_inicio)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            horario_id INTEGER,
            servico TEXT,
            status TEXT NOT NULL DEFAULT 'agendado',
            origem TEXT DEFAULT 'site_publico',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cancelado_em TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (horario_id) REFERENCES horarios_disponiveis(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cliente_id INTEGER,
            agendamento_cliente_id INTEGER,
            tipo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (agendamento_cliente_id) REFERENCES agendamentos_clientes(id)
        )
    """)

    # Inserir usuário de demonstração para testes
    cursor.execute("""
        INSERT OR IGNORE INTO usuarios (nome, email, senha_hash, nome_comercio)
        VALUES (?, ?, ?, ?)
    """, ("Admin Demo", "admin@demo.com", "demo123", "Barbearia do Demo"))

    cursor.execute("""
        UPDATE usuarios
        SET plan_status = 'active'
        WHERE email = 'admin@demo.com' AND (plan_status IS NULL OR plan_status = 'trial')
    """)

    conn.commit()
    conn.close()
    print("Banco de dados inicializado com sucesso!")


# ──────────────────────────────────────────────
# Funções auxiliares de acesso a dados
# ──────────────────────────────────────────────

def buscar_usuario_por_email(email: str):
    """Busca um usuário pelo e-mail para autenticação."""
    conn = get_connection()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return usuario


def buscar_usuario_por_id(usuario_id: int):
    """Busca um usuario pelo ID salvo na sessao."""
    conn = get_connection()
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    conn.close()
    return usuario


def criar_usuario_trial(nome: str, email: str, senha: str, nome_comercio: str):
    """Cria um usuario com 7 dias gratis."""
    agora = datetime.utcnow()
    trial_ends = agora + timedelta(days=7)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usuarios
            (nome, email, senha_hash, nome_comercio,
             trial_started_at, trial_ends_at, plan_status)
        VALUES (?, ?, ?, ?, ?, ?, 'trial')
    """, (
        nome,
        email,
        senha,
        nome_comercio,
        agora.isoformat(timespec="seconds"),
        trial_ends.isoformat(timespec="seconds"),
    ))
    usuario_id = cursor.lastrowid
    conn.commit()
    usuario = cursor.execute(
        "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    conn.close()
    return usuario


def registrar_login(usuario_id: int):
    """Atualiza o horario do ultimo login."""
    conn = get_connection()
    conn.execute("""
        UPDATE usuarios
        SET ultimo_login_em = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (usuario_id,))
    conn.commit()
    conn.close()


def status_plano_usuario(usuario):
    """Retorna active, trial ou expired."""
    if not usuario:
        return "demo"
    if usuario["plan_status"] == "active":
        return "active"
    trial_ends_at = usuario["trial_ends_at"]
    if trial_ends_at:
        try:
            trial_ends = datetime.fromisoformat(trial_ends_at)
            if datetime.utcnow() <= trial_ends:
                return "trial"
        except ValueError:
            pass
    return "expired"


def criar_cliente_e_agendamento(usuario_id, nome, celular, tipo_servico,
                                 data_servico, intervalo_dias, mensagem, data_envio):
    """
    Insere um novo cliente (ou reutiliza existente) e cria o agendamento de lembrete.
    Retorna o ID do agendamento criado.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Verifica se o cliente já existe para este comerciante (pelo celular)
    cliente = cursor.execute(
        "SELECT id FROM clientes WHERE usuario_id = ? AND celular = ?",
        (usuario_id, celular)
    ).fetchone()

    if cliente:
        cliente_id = cliente["id"]
        # Atualiza o nome caso tenha mudado
        cursor.execute(
            "UPDATE clientes SET nome = ? WHERE id = ?", (nome, cliente_id)
        )
    else:
        # Cria novo cliente
        cursor.execute(
            "INSERT INTO clientes (usuario_id, nome, celular) VALUES (?, ?, ?)",
            (usuario_id, nome, celular)
        )
        cliente_id = cursor.lastrowid

    # Cria o agendamento
    cursor.execute("""
        INSERT INTO agendamentos
            (usuario_id, cliente_id, tipo_servico, data_servico,
             intervalo_dias, data_envio, mensagem_personalizada)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (usuario_id, cliente_id, tipo_servico, data_servico,
          intervalo_dias, data_envio, mensagem))

    agendamento_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agendamento_id


def listar_agendamentos(usuario_id: int):
    """Retorna todos os agendamentos do comerciante com dados do cliente."""
    conn = get_connection()
    agendamentos = conn.execute("""
        SELECT
            a.id,
            c.nome AS cliente_nome,
            c.celular AS cliente_celular,
            a.tipo_servico,
            a.data_servico,
            a.intervalo_dias,
            a.data_envio,
            a.status,
            a.enviado_em,
            a.mensagem_personalizada
        FROM agendamentos a
        JOIN clientes c ON c.id = a.cliente_id
        WHERE a.usuario_id = ?
        ORDER BY a.data_envio ASC
    """, (usuario_id,)).fetchall()
    conn.close()
    return agendamentos


def buscar_agendamentos_para_hoje():
    """
    Retorna todos os agendamentos com data_envio = hoje e status 'pendente'.
    Usado pelo script de disparo automático.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    agendamentos = conn.execute("""
        SELECT
            a.id,
            a.mensagem_personalizada,
            a.tipo_servico,
            c.nome AS cliente_nome,
            c.celular AS cliente_celular
        FROM agendamentos a
        JOIN clientes c ON c.id = a.cliente_id
        WHERE a.data_envio = ? AND a.status = 'pendente'
    """, (hoje,)).fetchall()
    conn.close()
    return agendamentos


def marcar_como_enviado(agendamento_id: int):
    """Atualiza o status do agendamento para 'enviado'."""
    conn = get_connection()
    conn.execute("""
        UPDATE agendamentos
        SET status = 'enviado', enviado_em = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (agendamento_id,))
    conn.commit()
    conn.close()


def atualizar_whatsapp_profissional(usuario_id: int, whatsapp: str):
    """Salva o WhatsApp profissional do estabelecimento."""
    conn = get_connection()
    conn.execute("""
        UPDATE usuarios
        SET whatsapp_profissional = ?
        WHERE id = ?
    """, (whatsapp, usuario_id))
    conn.commit()
    conn.close()


def buscar_ou_criar_cliente(usuario_id: int, nome: str, celular: str):
    """Busca cliente pelo celular ou cria um novo dentro da conta do lojista."""
    conn = get_connection()
    cursor = conn.cursor()
    cliente = cursor.execute(
        "SELECT * FROM clientes WHERE usuario_id = ? AND celular = ?",
        (usuario_id, celular),
    ).fetchone()

    if cliente:
        cursor.execute("UPDATE clientes SET nome = ? WHERE id = ?", (nome, cliente["id"]))
        conn.commit()
        cliente = cursor.execute("SELECT * FROM clientes WHERE id = ?", (cliente["id"],)).fetchone()
        conn.close()
        return cliente

    cursor.execute(
        "INSERT INTO clientes (usuario_id, nome, celular) VALUES (?, ?, ?)",
        (usuario_id, nome, celular),
    )
    cliente_id = cursor.lastrowid
    conn.commit()
    cliente = cursor.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
    conn.close()
    return cliente


def registrar_historico(usuario_id: int, tipo: str, descricao: str,
                        cliente_id=None, agendamento_cliente_id=None):
    """Registra um evento no historico da conta."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO historico_eventos
            (usuario_id, cliente_id, agendamento_cliente_id, tipo, descricao)
        VALUES (?, ?, ?, ?, ?)
    """, (usuario_id, cliente_id, agendamento_cliente_id, tipo, descricao))
    conn.commit()
    conn.close()


def listar_historico(usuario_id: int, limite: int = 30):
    """Lista os eventos recentes do estabelecimento."""
    conn = get_connection()
    historico = conn.execute("""
        SELECT h.*, c.nome AS cliente_nome, c.celular AS cliente_celular
        FROM historico_eventos h
        LEFT JOIN clientes c ON c.id = h.cliente_id
        WHERE h.usuario_id = ?
        ORDER BY h.criado_em DESC
        LIMIT ?
    """, (usuario_id, limite)).fetchall()
    conn.close()
    return historico


def garantir_horarios_padrao(usuario_id: int, dias_a_frente: int = 21):
    """
    Cria uma grade simples se a conta ainda nao tiver horarios.
    Segunda a sexta: 08:00-18:00; sabado: 08:00-12:00.
    """
    conn = get_connection()
    cursor = conn.cursor()
    total = cursor.execute(
        "SELECT COUNT(*) AS total FROM horarios_disponiveis WHERE usuario_id = ?",
        (usuario_id,),
    ).fetchone()["total"]

    if total:
        conn.close()
        return

    hoje = datetime.now().date()
    for offset in range(dias_a_frente):
        dia = hoje + timedelta(days=offset)
        weekday = dia.weekday()
        if weekday >= 6:
            continue
        inicio = 8
        fim = 12 if weekday == 5 else 18
        for hora in range(inicio, fim):
            cursor.execute("""
                INSERT OR IGNORE INTO horarios_disponiveis
                    (usuario_id, data, hora_inicio, hora_fim, status)
                VALUES (?, ?, ?, ?, 'livre')
            """, (
                usuario_id,
                dia.strftime("%Y-%m-%d"),
                f"{hora:02d}:00",
                f"{hora + 1:02d}:00",
            ))

    conn.commit()
    conn.close()


def listar_horarios_livres(usuario_id: int, limite: int = 30):
    """Lista horarios livres futuros."""
    conn = get_connection()
    horarios = conn.execute("""
        SELECT * FROM horarios_disponiveis
        WHERE usuario_id = ?
          AND status = 'livre'
          AND data >= DATE('now', 'localtime')
        ORDER BY data ASC, hora_inicio ASC
        LIMIT ?
    """, (usuario_id, limite)).fetchall()
    conn.close()
    return horarios


def criar_agendamento_publico(usuario_id: int, nome: str, celular: str,
                              servico: str, horario_id: int):
    """Reserva um horario vindo do link publico da agenda."""
    conn = get_connection()
    cursor = conn.cursor()
    horario = cursor.execute("""
        SELECT * FROM horarios_disponiveis
        WHERE id = ? AND usuario_id = ? AND status = 'livre'
    """, (horario_id, usuario_id)).fetchone()

    if not horario:
        conn.close()
        return None

    cliente = cursor.execute(
        "SELECT * FROM clientes WHERE usuario_id = ? AND celular = ?",
        (usuario_id, celular),
    ).fetchone()
    if cliente:
        cliente_id = cliente["id"]
        cursor.execute("UPDATE clientes SET nome = ? WHERE id = ?", (nome, cliente_id))
    else:
        cursor.execute(
            "INSERT INTO clientes (usuario_id, nome, celular) VALUES (?, ?, ?)",
            (usuario_id, nome, celular),
        )
        cliente_id = cursor.lastrowid

    cursor.execute("""
        UPDATE horarios_disponiveis
        SET status = 'reservado', atualizado_em = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (horario_id,))
    cursor.execute("""
        INSERT INTO agendamentos_clientes
            (usuario_id, cliente_id, horario_id, servico, status, origem)
        VALUES (?, ?, ?, ?, 'agendado', 'site_publico')
    """, (usuario_id, cliente_id, horario_id, servico))
    agendamento_id = cursor.lastrowid

    descricao = (
        f"{nome} marcou {servico or 'atendimento'} para "
        f"{horario['data']} as {horario['hora_inicio']}."
    )
    cursor.execute("""
        INSERT INTO historico_eventos
            (usuario_id, cliente_id, agendamento_cliente_id, tipo, descricao)
        VALUES (?, ?, ?, 'agendamento_criado', ?)
    """, (usuario_id, cliente_id, agendamento_id, descricao))

    conn.commit()
    resultado = cursor.execute("""
        SELECT ac.*, c.nome AS cliente_nome, c.celular AS cliente_celular,
               hd.data, hd.hora_inicio, hd.hora_fim
        FROM agendamentos_clientes ac
        JOIN clientes c ON c.id = ac.cliente_id
        JOIN horarios_disponiveis hd ON hd.id = ac.horario_id
        WHERE ac.id = ?
    """, (agendamento_id,)).fetchone()
    conn.close()
    return resultado


def listar_agendamentos_clientes(usuario_id: int, limite: int = 30):
    """Lista agendamentos feitos pelo site publico."""
    conn = get_connection()
    agendamentos = conn.execute("""
        SELECT ac.*, c.nome AS cliente_nome, c.celular AS cliente_celular,
               hd.data, hd.hora_inicio, hd.hora_fim
        FROM agendamentos_clientes ac
        JOIN clientes c ON c.id = ac.cliente_id
        LEFT JOIN horarios_disponiveis hd ON hd.id = ac.horario_id
        WHERE ac.usuario_id = ?
        ORDER BY ac.criado_em DESC
        LIMIT ?
    """, (usuario_id, limite)).fetchall()
    conn.close()
    return agendamentos


def cancelar_agendamento_cliente(usuario_id: int, agendamento_id: int):
    """Cancela um agendamento publico e libera o horario."""
    conn = get_connection()
    cursor = conn.cursor()
    agendamento = cursor.execute("""
        SELECT ac.*, c.nome AS cliente_nome, hd.data, hd.hora_inicio
        FROM agendamentos_clientes ac
        JOIN clientes c ON c.id = ac.cliente_id
        LEFT JOIN horarios_disponiveis hd ON hd.id = ac.horario_id
        WHERE ac.id = ? AND ac.usuario_id = ? AND ac.status = 'agendado'
    """, (agendamento_id, usuario_id)).fetchone()

    if not agendamento:
        conn.close()
        return None

    if agendamento["horario_id"]:
        cursor.execute("""
            UPDATE horarios_disponiveis
            SET status = 'livre', atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (agendamento["horario_id"],))

    cursor.execute("""
        UPDATE agendamentos_clientes
        SET status = 'cancelado', cancelado_em = CURRENT_TIMESTAMP,
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (agendamento_id,))

    descricao = (
        f"{agendamento['cliente_nome']} desmarcou o horario de "
        f"{agendamento['data']} as {agendamento['hora_inicio']}."
    )
    cursor.execute("""
        INSERT INTO historico_eventos
            (usuario_id, cliente_id, agendamento_cliente_id, tipo, descricao)
        VALUES (?, ?, ?, 'agendamento_cancelado', ?)
    """, (usuario_id, agendamento["cliente_id"], agendamento_id, descricao))

    conn.commit()
    conn.close()
    return agendamento

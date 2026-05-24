"""
models.py - Configuração do banco de dados SQLite e definição das tabelas
Usando sqlite3 nativo do Python para manter o projeto leve e sem dependências extras
"""

import sqlite3
import os
from datetime import datetime

# Caminho do arquivo do banco de dados
DB_PATH = os.path.join(os.path.dirname(__file__), "retencao.db")


def get_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas pelo nome
    return conn


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

    # Inserir usuário de demonstração para testes
    cursor.execute("""
        INSERT OR IGNORE INTO usuarios (nome, email, senha_hash, nome_comercio)
        VALUES (?, ?, ?, ?)
    """, ("Admin Demo", "admin@demo.com", "demo123", "Barbearia do Demo"))

    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado com sucesso!")


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

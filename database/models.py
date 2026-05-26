"""
database/models.py

Camada de acesso a dados — SQLite com suporte a WAL.
Todas as tabelas do VoltaCliente Conchal com as 5 regras de negócio.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "retencao.db")

# Constantes de configuração
DEMO_MINUTOS = 10
TRIAL_DIAS = 7
HANDOFF_HORAS = 12
CICLO_COBRANCA_DIAS = 30


@contextmanager
def get_db():
    """Context manager para conexão com banco de dados."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Cria todas as tabelas necessárias com as 5 regras de negócio."""
    with get_db() as conn:
        conn.executescript("""
        -- ═══════════════════════════════════════════════════════════════════
        -- 1️⃣ USUÁRIOS (Donos do Estabelecimento)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nome TEXT NOT NULL,
            nome_estabelecimento TEXT,
            tipo_negocio TEXT DEFAULT 'barbearia',
            
            -- 🎯 RULE 1: Trial + Paywall
            trial_start TEXT,                    -- Data de início do trial (ISO 8601)
            trial_expiry TEXT,                   -- Data de expiração (ISO 8601)
            subscription_status TEXT DEFAULT 'trialing',  -- trialing|active|past_due|canceled
            
            -- 🎯 RULE 3: WhatsApp Integration
            whatsapp_number TEXT,                -- Número do dono (55119...)
            whatsapp_verified INTEGER DEFAULT 0, -- 1 = verificado via Evolution API
            
            -- 🎯 RULE 4: Slug Único
            slug TEXT UNIQUE,                    -- Link público: /agendar/<slug>
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 2️⃣ ASSINATURAS (Rule 2: Automação de Cobrança)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            
            -- Dados da subscrição
            stripe_id TEXT,                      -- ID do Mercado Pago ou Stripe
            status TEXT DEFAULT 'trialing',      -- trialing|active|past_due|canceled
            plan TEXT DEFAULT 'pro',             -- free|pro|premium
            amount_cents INTEGER DEFAULT 3000,   -- R$ 30,00 em centavos
            billing_cycle_day INTEGER DEFAULT 7, -- Dia do mês para cobrança (7, 15 ou 30)
            
            -- Datas importantes
            trial_starts TEXT,
            trial_ends TEXT,
            current_period_start TEXT,
            current_period_end TEXT,
            next_billing_date TEXT,              -- Próxima cobrança
            
            -- Histórico de pagamentos
            last_payment_date TEXT,
            last_payment_id TEXT,
            failed_payment_count INTEGER DEFAULT 0,
            last_failed_date TEXT,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_next_billing ON subscriptions(next_billing_date);
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 3️⃣ CLIENTES (Agendados pelo Estabelecimento)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            
            nome TEXT NOT NULL,
            whatsapp TEXT NOT NULL,              -- Celular do cliente final
            email TEXT,
            tipo_servico TEXT,
            intervalo_retorno INTEGER DEFAULT 30,
            
            data_ultimo_servico TEXT,
            data_proximo_contato TEXT,
            status TEXT DEFAULT 'ativo',         -- ativo|inativo
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_clientes_user_id ON clientes(user_id);
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 4️⃣ AGENDAMENTOS / LEMBRETES
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS fila_envios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            
            cliente_nome TEXT NOT NULL,
            cliente_celular TEXT NOT NULL,
            tipo_mensagem TEXT,                  -- reminder|confirmacao|followup
            mensagem TEXT,
            
            data_agendada TEXT,                  -- Quando enviar (ISO 8601)
            data_enviada TEXT,
            
            status TEXT DEFAULT 'pendente',      -- pendente|enviado|erro|cancelado
            tentativas INTEGER DEFAULT 0,
            resposta_api TEXT,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_fila_status ON fila_envios(status);
        CREATE INDEX IF NOT EXISTS idx_fila_data_agendada ON fila_envios(data_agendada);
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 5️⃣ DISPONIBILIDADES (Rule 4: Agendamento Público - Prevenção Double-Booking)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS disponibilidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            
            dia_semana INTEGER,                  -- 0=domingo ... 6=sábado
            horario_inicio TEXT,                 -- HH:MM
            horario_fim TEXT,                    -- HH:MM
            
            ativo INTEGER DEFAULT 1,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 6️⃣ AGENDAMENTOS PÚBLICOS (Rule 4: Link de Agendamento)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS agendamentos_publicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            
            nome_cliente TEXT NOT NULL,
            celular_cliente TEXT NOT NULL,
            email_cliente TEXT,
            
            data_agendada TEXT NOT NULL,         -- YYYY-MM-DD
            horario_agendado TEXT NOT NULL,      -- HH:MM
            
            servico TEXT,
            observacoes TEXT,
            
            status TEXT DEFAULT 'confirmado',    -- confirmado|cancelado|completo
            
            -- Link de confirmação
            token_confirmacao TEXT UNIQUE,
            confirmado_at TEXT,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_agendamentos_user_data ON agendamentos_publicos(user_id, data_agendada);
        CREATE INDEX IF NOT EXISTS idx_agendamentos_status ON agendamentos_publicos(status);
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 7️⃣ IA + WHATSAPP (Rule 3: Conversas e Handoff)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS conversas_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cliente_celular TEXT NOT NULL,
            
            -- Histórico de mensagens
            mensagens TEXT,                      -- JSON array: [{"role":"user"|"assistant", "content":"...", "timestamp":"..."}]
            
            -- Estado do handoff
            ia_ativa INTEGER DEFAULT 1,          -- 1 = IA respondendo, 0 = dono respondendo
            ia_pausada_ate TEXT,                 -- Se pausada, até quando (ISO 8601)
            dono_respondeu_em TEXT,              -- Quando o dono última vez respondeu
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_conversas_user_celular ON conversas_ia(user_id, cliente_celular);
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 8️⃣ NOTIFICAÇÕES (Rule 5: Web + Mobile Push)
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS notificacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            
            tipo TEXT,                           -- agendamento|pagamento|lembrete|sistema
            titulo TEXT NOT NULL,
            conteudo TEXT,
            
            -- Canais de entrega
            enviado_web INTEGER DEFAULT 0,       -- WebSocket/In-app
            enviado_push INTEGER DEFAULT 0,      -- Web Push Notification
            enviado_email INTEGER DEFAULT 0,     -- SMTP
            enviado_whatsapp INTEGER DEFAULT 0,  -- Evolution API
            
            -- Status
            lido INTEGER DEFAULT 0,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_notificacoes_user ON notificacoes(user_id);
        
        -- ══════════════════════════��════════════════════════════════════════
        -- 9️⃣ DEMO MODE
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS demo_ips (
            ip TEXT PRIMARY KEY,
            iniciado_em TEXT NOT NULL
        );
        
        -- ═══════════════════════════════════════════════════════════════════
        -- 🔟 LOGS DE PAGAMENTO
        -- ═══════════════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS payment_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            
            external_id TEXT,                    -- ID do Mercado Pago/Stripe
            amount_cents INTEGER,
            currency TEXT DEFAULT 'BRL',
            status TEXT,                         -- pending|approved|failed|refunded
            
            metadata TEXT,                       -- JSON com detalhes adicionais
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 RULE 1: TRIAL + PAYWALL
# ═══════════════════════════════════════════════════════════════════════════════

def criar_usuario(email, password, nome, nome_estabelecimento, tipo_negocio):
    """Cria novo usuário com trial de 7 dias ativado."""
    with get_db() as conn:
        agora = datetime.now()
        trial_start = agora.isoformat()
        trial_expiry = (agora + timedelta(days=TRIAL_DIAS)).isoformat()
        
        cursor = conn.execute('''
            INSERT INTO users (
                email, password, nome, nome_estabelecimento, tipo_negocio,
                trial_start, trial_expiry, subscription_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (email, password, nome, nome_estabelecimento, tipo_negocio,
              trial_start, trial_expiry, 'trialing'))
        
        user_id = cursor.lastrowid
        
        # Criar subscription
        conn.execute('''
            INSERT INTO subscriptions (
                user_id, trial_starts, trial_ends, status,
                next_billing_date
            ) VALUES (?, ?, ?, ?, ?)
        ''', (user_id, trial_start, trial_expiry, 'trialing',
              (agora + timedelta(days=TRIAL_DIAS)).isoformat()))
        
        conn.commit()
        return user_id


def verificar_trial_valido(user_id):
    """Verifica se o usuário ainda está em trial ativo."""
    with get_db() as conn:
        user = conn.execute(
            'SELECT trial_expiry, subscription_status FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        
        if not user:
            return False
        
        agora = datetime.now().isoformat()
        # Trial válido se: status = trialing E agora < trial_expiry
        return (user['subscription_status'] == 'trialing' and 
                agora < user['trial_expiry'])


def obter_status_assinatura(user_id):
    """Retorna o status atual da assinatura."""
    with get_db() as conn:
        sub = conn.execute(
            'SELECT status, subscription_status, trial_expiry FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        return dict(sub) if sub else None


# ═══════════════════════════════════════════════════════════════════════════════
# 2️⃣ RULE 2: AUTOMAÇÃO DE COBRANÇA
# ═══════════════════════════════════════════════════════════════════════════════

def buscar_usuarios_para_cobranca(dia_mes):
    """Busca usuários que devem ser cobrados no dia especificado do mês."""
    with get_db() as conn:
        usuarios = conn.execute('''
            SELECT u.id, u.email, s.stripe_id, s.amount_cents
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE s.status IN ('active', 'past_due')
            AND s.billing_cycle_day = ?
        ''', (dia_mes,)).fetchall()
        
        return [dict(u) for u in usuarios]


def atualizar_status_assinatura(user_id, novo_status, next_billing_date=None):
    """Atualiza o status da assinatura."""
    with get_db() as conn:
        agora = datetime.now().isoformat()
        
        conn.execute('''
            UPDATE users SET subscription_status = ?, updated_at = ?
            WHERE id = ?
        ''', (novo_status, agora, user_id))
        
        update_sub = 'UPDATE subscriptions SET status = ?, updated_at = ?'
        params = [novo_status, agora]
        
        if next_billing_date:
            update_sub += ', next_billing_date = ?'
            params.append(next_billing_date)
        
        update_sub += ' WHERE user_id = ?'
        params.append(user_id)
        
        conn.execute(update_sub, params)
        conn.commit()


def registrar_pagamento(user_id, external_id, amount_cents, status, metadata=None):
    """Registra um pagamento realizado."""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO payment_logs (user_id, external_id, amount_cents, status, metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, external_id, amount_cents, status, json.dumps(metadata or {})))
        
        if status == 'approved':
            # Próxima cobrança em 30 dias
            proxima = (datetime.now() + timedelta(days=30)).isoformat()
            conn.execute(
                'UPDATE subscriptions SET last_payment_date = ?, last_payment_id = ?, next_billing_date = ? WHERE user_id = ?',
                (datetime.now().isoformat(), external_id, proxima, user_id)
            )
        
        conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 3️⃣ RULE 3: WHATSAPP + IA
# ═══════════════════════════════════════════════════════════════════════════════

def obter_ou_criar_conversa(user_id, cliente_celular):
    """Obtém ou cria uma conversa com um cliente."""
    with get_db() as conn:
        conversa = conn.execute('''
            SELECT * FROM conversas_ia
            WHERE user_id = ? AND cliente_celular = ?
        ''', (user_id, cliente_celular)).fetchone()
        
        if conversa:
            return dict(conversa)
        
        # Criar nova conversa
        agora = datetime.now().isoformat()
        cursor = conn.execute('''
            INSERT INTO conversas_ia (user_id, cliente_celular, mensagens, ia_ativa)
            VALUES (?, ?, ?, ?)
        ''', (user_id, cliente_celular, json.dumps([]), 1))
        
        conn.commit()
        return {
            'id': cursor.lastrowid,
            'user_id': user_id,
            'cliente_celular': cliente_celular,
            'mensagens': [],
            'ia_ativa': 1
        }


def adicionar_mensagem_conversa(conversa_id, role, conteudo):
    """Adiciona uma mensagem ao histórico da conversa."""
    with get_db() as conn:
        conversa = conn.execute(
            'SELECT mensagens FROM conversas_ia WHERE id = ?',
            (conversa_id,)
        ).fetchone()
        
        mensagens = json.loads(conversa['mensagens'] or '[]')
        mensagens.append({
            'role': role,
            'content': conteudo,
            'timestamp': datetime.now().isoformat()
        })
        
        conn.execute(
            'UPDATE conversas_ia SET mensagens = ?, updated_at = ? WHERE id = ?',
            (json.dumps(mensagens), datetime.now().isoformat(), conversa_id)
        )
        conn.commit()


def ativar_handoff_dono(conversa_id, duracao_horas=HANDOFF_HORAS):
    """Pausa IA por 12h quando dono responde (handoff)."""
    with get_db() as conn:
        ia_pausada_ate = (datetime.now() + timedelta(hours=duracao_horas)).isoformat()
        
        conn.execute('''
            UPDATE conversas_ia 
            SET ia_ativa = 0, ia_pausada_ate = ?, dono_respondeu_em = ?
            WHERE id = ?
        ''', (ia_pausada_ate, datetime.now().isoformat(), conversa_id))
        
        conn.commit()


def reativar_ia_se_necessario(conversa_id):
    """Reativa IA se o período de pausa já passou."""
    with get_db() as conn:
        conversa = conn.execute(
            'SELECT ia_pausada_ate FROM conversas_ia WHERE id = ?',
            (conversa_id,)
        ).fetchone()
        
        if conversa and conversa['ia_pausada_ate']:
            agora = datetime.now().isoformat()
            if agora >= conversa['ia_pausada_ate']:
                conn.execute(
                    'UPDATE conversas_ia SET ia_ativa = 1 WHERE id = ?',
                    (conversa_id,)
                )
                conn.commit()
                return True
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 4️⃣ RULE 4: LINK ÚNICO + AGENDAMENTO PÚBLICO
# ═══════════════════════════════════════════════════════════════════════════════

def gerar_slug_unico(nome_estabelecimento):
    """Gera um slug único baseado no nome do estabelecimento."""
    import re
    slug_base = re.sub(r'[^a-z0-9]+', '-', nome_estabelecimento.lower()).strip('-')
    
    with get_db() as conn:
        # Verificar se slug já existe
        existing = conn.execute(
            'SELECT COUNT(*) as count FROM users WHERE slug LIKE ?',
            (f'{slug_base}%',)
        ).fetchone()
        
        if existing['count'] == 0:
            return slug_base
        
        # Adicionar número se necessário
        for i in range(1, 1000):
            slug_candidato = f'{slug_base}-{i}'
            exists = conn.execute(
                'SELECT COUNT(*) as count FROM users WHERE slug = ?',
                (slug_candidato,)
            ).fetchone()
            
            if exists['count'] == 0:
                return slug_candidato
        
        return slug_base


def obter_usuario_por_slug(slug):
    """Busca um usuário pelo slug público."""
    with get_db() as conn:
        usuario = conn.execute(
            'SELECT * FROM users WHERE slug = ?',
            (slug,)
        ).fetchone()
        return dict(usuario) if usuario else None


def agendar_cliente(user_id, nome, celular, email, data, horario, servico=None):
    """
    Agenda um cliente de forma segura (previne double-booking com transação).
    """
    with get_db() as conn:
        # Verificar se já existe agendamento nesse horário
        ja_agendado = conn.execute('''
            SELECT COUNT(*) as count FROM agendamentos_publicos
            WHERE user_id = ? AND data_agendada = ? AND horario_agendado = ? 
            AND status = 'confirmado'
        ''', (user_id, data, horario)).fetchone()
        
        if ja_agendado['count'] > 0:
            return None, 'Horário já foi agendado'
        
        # Gerar token de confirmação
        import secrets
        token = secrets.token_urlsafe(32)
        
        cursor = conn.execute('''
            INSERT INTO agendamentos_publicos (
                user_id, nome_cliente, celular_cliente, email_cliente,
                data_agendada, horario_agendado, servico, token_confirmacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, nome, celular, email, data, horario, servico, token))
        
        conn.commit()
        return cursor.lastrowid, None


def obter_horarios_disponiveis(user_id, data):
    """Busca horários disponíveis para um dia específico."""
    with get_db() as conn:
        from datetime import datetime as dt
        
        # Pegar disponibilidades do usuário
        data_obj = dt.fromisoformat(data)
        dia_semana = data_obj.weekday()
        
        disponibilidades = conn.execute('''
            SELECT horario_inicio, horario_fim FROM disponibilidades
            WHERE user_id = ? AND dia_semana = ? AND ativo = 1
        ''', (user_id, dia_semana)).fetchall()
        
        # Pegar agendamentos já feitos nesse dia
        agendados = conn.execute('''
            SELECT horario_agendado FROM agendamentos_publicos
            WHERE user_id = ? AND data_agendada = ? AND status = 'confirmado'
        ''', (user_id, data)).fetchall()
        
        agendados_set = {a['horario_agendado'] for a in agendados}
        
        # Retornar horários disponíveis
        horarios = []
        for disp in disponibilidades:
            # Gerar intervalos de 30 min entre inicio e fim
            inicio = dt.strptime(disp['horario_inicio'], '%H:%M')
            fim = dt.strptime(disp['horario_fim'], '%H:%M')
            
            atual = inicio
            while atual < fim:
                horario_str = atual.strftime('%H:%M')
                if horario_str not in agendados_set:
                    horarios.append(horario_str)
                atual = dt(atual.year, atual.month, atual.day,
                          atual.hour, atual.minute + 30)
        
        return sorted(set(horarios))


# ═══════════════════════════════════════════════════════════════════════════════
# 5️⃣ RULE 5: NOTIFICAÇÕES
# ═══════════════════════════════════════════════════════════════════════════════

def criar_notificacao(user_id, tipo, titulo, conteudo, canais=['web']):
    """Cria uma notificação em um ou mais canais."""
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO notificacoes (user_id, tipo, titulo, conteudo)
            VALUES (?, ?, ?, ?)
        ''', (user_id, tipo, titulo, conteudo))
        
        notif_id = cursor.lastrowid
        
        # Marcar canais
        update_sql = 'UPDATE notificacoes SET'
        updates = []
        for canal in canais:
            updates.append(f'enviado_{canal} = 1')
        
        if updates:
            update_sql += ' ' + ', '.join(updates) + ' WHERE id = ?'
            conn.execute(update_sql, (notif_id,))
        
        conn.commit()
        return notif_id


def obter_notificacoes(user_id, limite=20):
    """Busca notificações de um usuário (mais recentes primeiro)."""
    with get_db() as conn:
        notifs = conn.execute('''
            SELECT * FROM notificacoes
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limite)).fetchall()
        
        return [dict(n) for n in notifs]


# ═══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════════

def buscar_agendamentos_para_hoje():
    """Busca lembretes que venceram hoje (para disparador.py)."""
    with get_db() as conn:
        hoje = datetime.now().strftime('%Y-%m-%d')
        
        agendamentos = conn.execute('''
            SELECT * FROM fila_envios
            WHERE DATE(data_agendada) = ? AND status = 'pendente'
        ''', (hoje,)).fetchall()
        
        return [dict(a) for a in agendamentos]


def marcar_como_enviado(fila_id, resposta_api=None):
    """Marca um envio como completo."""
    with get_db() as conn:
        conn.execute('''
            UPDATE fila_envios
            SET status = 'enviado', data_enviada = ?, resposta_api = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), resposta_api or '', fila_id))
        
        conn.commit()

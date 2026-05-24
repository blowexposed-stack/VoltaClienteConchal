# 💬 RetençãoPRO — Micro-SaaS de Retenção de Clientes via WhatsApp

MVP para barbearias, salões de beleza e pet shops manterem clientes ativos
enviando lembretes automáticos via WhatsApp no prazo certo.

---

## 🚀 Como rodar localmente

### 1. Instale as dependências
```bash
pip install -r requirements.txt
```

### 2. Inicie o servidor
```bash
python app.py
```

### 3. Acesse no navegador
```
http://localhost:5000
```

### 4. Login de demonstração
```
E-mail : admin@demo.com
Senha  : demo123
```

---

## 📁 Estrutura de pastas

```
saas-retencao/
├── app.py                  # Backend Flask (rotas, autenticação, lógica)
├── disparador.py           # Script de disparo automático (rodar via cron)
├── requirements.txt        # Dependências Python
├── database/
│   ├── models.py           # Modelos SQLite e funções de acesso a dados
│   └── retencao.db         # Banco de dados (criado automaticamente)
└── templates/
    ├── login.html          # Tela de login
    └── dashboard.html      # Tela principal (cadastro + fila de envios)
```

---

## ⚙️ Configurando o disparo automático

### Linux/Mac (cron job — todo dia às 9h):
```bash
crontab -e
# Adicione a linha:
0 9 * * * cd /caminho/do/projeto && python disparador.py
```

### Windows (Agendador de Tarefas):
- Programa: `python`
- Argumentos: `C:\caminho\do\projeto\disparador.py`
- Gatilho: Diário às 9h

---

## 📱 Integrando API real do WhatsApp

Abra o arquivo `disparador.py` e substitua a função `enviar_whatsapp()`.
As instruções para Evolution API, Z-API e Twilio já estão documentadas
nos comentários dentro da função.

---

## 🔐 Segurança para produção

Antes de publicar online:
1. Troque `app.secret_key` em `app.py` por uma string aleatória longa
2. Implemente hash de senhas com `bcrypt` em vez de texto puro
3. Use variáveis de ambiente para credenciais (`.env` + `python-dotenv`)
4. Considere migrar para PostgreSQL para múltiplos usuários simultâneos

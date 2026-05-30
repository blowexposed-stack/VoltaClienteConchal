# 💬 VoltaCliente Conchal — Micro-SaaS de Retenção via WhatsApp

## 🚀 Rodar localmente
```bash
pip install -r requirements.txt
python app.py
# http://localhost:5000
# Demo: admin@demo.com / demo123
```

## 📁 Estrutura
```
├── app.py                  # Backend Flask — todas as rotas
├── disparador.py           # Cron job de envio diário (IA gera mensagens)
├── notificacoes.py         # Notificação SMTP ao admin
├── requirements.txt
├── Procfile / runtime.txt
├── database/
│   └── models.py           # SQLite — todas as tabelas e queries
└── templates/
    ├── login.html           # Tela de acesso + cadastro + timer demo
    ├── dashboard.html       # Painel com 4 abas
    ├── agenda_publica.html  # Página pública /agendar/<slug> — 3 etapas
    ├── pagamento.html       # Paywall pós-trial
    └── 404.html
```

## 🔒 Funil anti-fraude
1. Demo 10 min por IP (F5 não reinicia — clock persiste no banco)
2. Ao expirar → redireciona para login automaticamente
3. Cadastro bloqueado por IP (1 conta por IP)
4. Trial 7 dias grátis após cadastro
5. Paywall Mercado Pago após trial

## 🤖 Lembretes automáticos (IA)
- Ao cadastrar cliente, marque os ciclos: **7, 15 e/ou 30 dias**
- O `disparador.py` roda diariamente e a IA (Anthropic) gera a mensagem personalizada
- Inclui nome, serviço e link de agendamento automaticamente

## 📱 Chatbot WhatsApp (Evolution API + IA)
- Salve o número do negócio no painel
- Configure o webhook na Evolution API: `https://seuapp.com/webhook/<slug>`
- Evento: `messages.upsert`
- Cliente manda mensagem → IA responde com link de agendamento
- Dono digita → IA pausa por 12h (handoff automático)
- Após 12h → IA retoma sozinha

## ⚙️ Variáveis de ambiente (Render)
| Variável | Descrição |
|---|---|
| `SECRET_KEY` | Chave Flask (string longa aleatória) |
| `BASE_URL` | URL pública (ex: https://seuapp.onrender.com) |
| `ANTHROPIC_API_KEY` | Chave Anthropic (IA) |
| `EVOLUTION_URL` | URL da Evolution API |
| `EVOLUTION_APIKEY` | API Key da Evolution |
| `EVOLUTION_INST` | Nome da instância Evolution |
| `MP_ACCESS_TOKEN` | Token Mercado Pago |
| `MP_CHECKOUT_URL` | URL do checkout MP |
| `PLANO_VALOR` | Valor exibido (ex: R$ 30,00) |
| `SMTP_HOST/USER/PASSWORD` | Para notificações de login |
| `ADMIN_NOTIFY_EMAIL` | E-mail do admin |

## ⏰ Cron job (Render — Cron Jobs)
```
0 9 * * *   python disparador.py
```

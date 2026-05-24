"""
notificacoes.py

Modulo de notificacoes administrativas do VoltaCliente Conchal.
Usa SMTP padrao do Python para evitar dependencias extras.
"""

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage


ADMIN_NOTIFY_EMAIL = os.environ.get(
    "ADMIN_NOTIFY_EMAIL",
    "rafaelsouzahqd@gmail.com",
)


def notificar_login_admin(usuario, metodo="login"):
    """
    Envia um e-mail para o dono do SaaS quando alguem acessa a conta.

    Para funcionar no Render, configure:
    - SMTP_HOST
    - SMTP_PORT
    - SMTP_USER
    - SMTP_PASSWORD
    - SMTP_FROM_EMAIL
    - ADMIN_NOTIFY_EMAIL

    Se as variaveis SMTP nao estiverem configuradas, a funcao apenas registra
    no log e nao quebra o login do usuario.
    """
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM_EMAIL", smtp_user or ADMIN_NOTIFY_EMAIL)

    if not all([smtp_host, smtp_user, smtp_password, smtp_from]):
        print("[NOTIFICACAO] SMTP nao configurado; login nao enviado por e-mail.")
        return False

    nome = usuario["nome"] if "nome" in usuario.keys() else "Usuario"
    email = usuario["email"] if "email" in usuario.keys() else "sem-email"
    comercio = usuario["nome_comercio"] if "nome_comercio" in usuario.keys() else "-"
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    mensagem = EmailMessage()
    mensagem["Subject"] = f"Novo login no VoltaCliente Conchal: {nome}"
    mensagem["From"] = smtp_from
    mensagem["To"] = ADMIN_NOTIFY_EMAIL
    mensagem.set_content(
        "\n".join([
            "Novo acesso ao VoltaCliente Conchal.",
            "",
            f"Nome: {nome}",
            f"E-mail: {email}",
            f"Comercio: {comercio}",
            f"Metodo: {metodo}",
            f"Data/hora: {agora}",
        ])
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
            servidor.starttls()
            servidor.login(smtp_user, smtp_password)
            servidor.send_message(mensagem)
        return True
    except Exception as erro:
        print(f"[NOTIFICACAO] Falha ao enviar e-mail de login: {erro}")
        return False

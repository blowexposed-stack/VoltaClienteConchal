"""
whatsapp_integration.py - Integração com WhatsApp via Evolution API
"""

import requests
import json
from datetime import datetime, timezone
from typing import Dict, Optional
import logging
import os

logger = logging.getLogger(__name__)

class EvolutionWhatsAppAPI:
    """Cliente para Evolution API de WhatsApp"""
    
    def __init__(self, api_url: str, api_key: str, instance_name: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.instance_name = instance_name
        self.headers = {
            "apikey": api_key,
            "Content-Type": "application/json"
        }
    
    def enviar_mensagem_texto(self, numero: str, texto: str) -> bool:
        """
        Envia mensagem de texto via WhatsApp
        
        Args:
            numero: Número sem país (ex: 11999999999)
            texto: Conteúdo da mensagem
        
        Returns:
            True se enviado, False caso contrário
        """
        try:
            url = f"{self.api_url}/message/sendText/{self.instance_name}"
            payload = {
                "number": f"55{numero}@s.whatsapp.net",
                "text": texto
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            
            if response.status_code == 201:
                logger.info(f"✅ WhatsApp enviado para {numero}")
                return True
            else:
                logger.error(f"❌ Erro ao enviar WhatsApp: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exceção ao enviar WhatsApp: {str(e)}")
            return False
    
    def enviar_mensagem_template(self, numero: str, template_id: str, parametros: list) -> bool:
        """Envia mensagem com template pré-aprovado"""
        try:
            url = f"{self.api_url}/message/sendTemplate/{self.instance_name}"
            payload = {
                "number": f"55{numero}@s.whatsapp.net",
                "template": {
                    "name": template_id,
                    "language": {"code": "pt_BR"},
                    "bodyParameters": parametros
                }
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            return response.status_code == 201
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar template: {str(e)}")
            return False
    
    def enviar_midia(self, numero: str, tipo: str, url_midia: str, legenda: str = "") -> bool:
        """
        Envia mídia (imagem, vídeo, áudio, documento)
        
        Args:
            numero: Número do WhatsApp
            tipo: 'image', 'video', 'audio', 'document'
            url_midia: URL pública da mídia
            legenda: Legenda/descrição
        """
        try:
            endpoint_map = {
                'image': 'sendImage',
                'video': 'sendVideo',
                'audio': 'sendAudio',
                'document': 'sendDocument'
            }
            
            endpoint = endpoint_map.get(tipo, 'sendImage')
            url = f"{self.api_url}/message/{endpoint}/{self.instance_name}"
            
            payload = {
                "number": f"55{numero}@s.whatsapp.net",
                "mediaUrl": url_midia,
                "caption": legenda if legenda else None
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            return response.status_code == 201
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mídia: {str(e)}")
            return False
    
    def processar_webhook(self, payload: Dict) -> Optional[Dict]:
        """
        Processa webhook recebido da Evolution API
        
        Returns:
            Dict com dados da mensagem ou None
        """
        try:
            # Esperado payload com:
            # {
            #   "event": "messages.upsert",
            #   "data": {
            #     "messages": [{
            #       "id": "...",
            #       "from": "5511999999999",
            #       "to": "...",
            #       "body": "Texto da mensagem",
            #       "timestamp": 1234567890
            #     }]
            #   }
            # }
            
            if payload.get('event') != 'messages.upsert':
                return None
            
            messages = payload.get('data', {}).get('messages', [])
            
            if not messages:
                return None
            
            msg = messages[0]
            
            # Remover país (55) do número
            numero = msg['from'].replace('55', '')
            
            return {
                'id': msg.get('id'),
                'numero': numero,
                'corpo': msg.get('body'),
                'timestamp': datetime.fromtimestamp(msg.get('timestamp', 0), tz=timezone.utc)
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar webhook: {str(e)}")
            return None

# ============ UTILITÁRIOS DE MENSAGEM ============

def gerar_mensagem_cobranca(nome_cliente: str, valor: float, url_pagamento: str) -> str:
    """Gera mensagem de cobrança amigável"""
    return f"""Olá {nome_cliente} 👋

Sua assinatura do VoltaCliente venceu!

💰 *Valor a pagar:* R$ {valor:.2f}

Clique no link abaixo para renovar:
{url_pagamento}

Dúvidas? Responda este WhatsApp que ajudamos! 🤝"""

def gerar_mensagem_confirmacao_agendamento(cliente_nome: str, data_hora: str, servico: str) -> str:
    """Gera mensagem de confirmação de agendamento"""
    return f"""✅ Agendamento confirmado!

Olá {cliente_nome}, seu agendamento foi confirmado:

📅 *Data/Hora:* {data_hora}
🛡️ *Serviço:* {servico}

Nos vemos em breve! 😊

Se precisar cancelar, avise com antecedência."""

def gerar_mensagem_lembrete_agendamento(cliente_nome: str, data_hora: str) -> str:
    """Gera mensagem de lembrete de agendamento próximo"""
    return f"""🔔 Lembrete de agendamento!

Olá {cliente_nome}, este é um lembrete do seu agendamento:

📅 *Data/Hora:* {data_hora}

Nos vemos em breve! 👋"""

def gerar_mensagem_cancelamento(cliente_nome: str, motivo: str = "") -> str:
    """Gera mensagem de cancelamento de agendamento"""
    msg = f"""❌ Agendamento cancelado

Olá {cliente_nome}, seu agendamento foi cancelado."""
    
    if motivo:
        msg += f"\n\n*Motivo:* {motivo}"
    
    msg += "\n\nSe quiser remarcar, é só nos chamar! 📞"
    
    return msg

# ============ CLASSE DE IA CHATBOT ============

class ChatbotAgendamentos:
    """Chatbot com IA para gerenciar agendamentos via WhatsApp"""
    
    def __init__(self, user_id: int, db):
        self.user_id = user_id
        self.db = db
        self.conversation_history = []
        
        # Buscar contexto do estabelecimento
        user = db.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        self.estabelecimento = user
    
    def processar_mensagem_whatsapp(self, numero_cliente: str, mensagem_texto: str) -> str:
        """
        Processa mensagem do cliente e retorna resposta
        
        Fluxo:
        1. Recebe mensagem
        2. Passa para IA interpretar intenção
        3. IA retorna resposta e ação
        4. Executa ação se necessário
        5. Retorna resposta
        """
        try:
            from anthropic import Anthropic
            
            self.conversation_history.append({
                "role": "user",
                "content": mensagem_texto
            })
            
            # Prompt do sistema com contexto
            prompt_sistema = f"""Você é um assistente de agendamentos para '{self.estabelecimento['nome_estabelecimento']}'.
Tipo de negócio: {self.estabelecimento['tipo_negocio']}

Seu objetivo é ajudar clientes a:
1. AGENDAR novos compromissos
2. CANCELAR agendamentos existentes
3. VER horários disponíveis
4. Responder DÚVIDAS sobre serviços

IMPORTANTE:
- Sempre responda em Português Brasileiro, amigável e profissional
- Use emojis quando apropriado
- Mensagens curtas (máx 160 caracteres por linha)
- Se for agendar, pergunte: DATA, HORÁRIO e SERVIÇO
- Nunca inventar informações
- Se não souber, ser honesto"""
            
            # Chamar Claude
            client = Anthropic()
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=300,
                system=prompt_sistema,
                messages=self.conversation_history
            )
            
            resposta_ia = response.content[0].text
            self.conversation_history.append({
                "role": "assistant",
                "content": resposta_ia
            })
            
            logger.info(f"🤖 IA respondeu para {numero_cliente}")
            return resposta_ia
            
        except Exception as e:
            logger.error(f"❌ Erro no chatbot: {str(e)}")
            return "Desculpe, tive um problema aqui. Tente novamente! 🙏"

# ============ HELPER FUNCTIONS ============

def limpar_numero_whatsapp(numero: str) -> str:
    """Remove formatação do número WhatsApp"""
    import re
    return re.sub(r'\D', '', numero)

def formatar_numero_whatsapp(numero: str) -> str:
    """Formata número para padrão WhatsApp (55XXXXXXXXXX)"""
    numero = limpar_numero_whatsapp(numero)
    
    if numero.startswith('55'):
        return numero
    
    if numero.startswith('0'):
        return f"55{numero[1:]}"
    
    return f"55{numero}"

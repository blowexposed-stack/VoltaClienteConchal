"""Executa o envio dos lembretes pendentes.

No Render, prefira chamar /cron/disparos com DISPARADOR_TOKEN para usar o banco
do Web Service. Este script fica como alternativa para execucao local.
"""

from app import executar_lembretes_pendentes


if __name__ == "__main__":
    resultado = executar_lembretes_pendentes()
    print(resultado)

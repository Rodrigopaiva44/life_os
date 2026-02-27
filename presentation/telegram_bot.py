"""
presentation/telegram_bot.py
==============================
Ponto de entrada do bot Telegram para o Life_OS.

Handlers implementados:
  - /start  → mensagem de boas-vindas.
  - voice   → baixa o .ogg, chama o Motor Cognitivo e persiste no banco via
              Executor, respondendo ao usuário com confirmação amigável.

Pipeline de uma mensagem de voz:
  Telegram  →  download .ogg
            →  processar_audio_para_json()   [LLM Router]
            →  persistir_dados()             [Executor]
            →  reply com mensagem amigável
"""

import logging
import os
import tempfile

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from application.executor import persistir_dados
from application.llm_router import processar_audio_para_json
from infrastructure.settings import settings

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=settings.log_level.upper(),
)
logger = logging.getLogger(__name__)

_WELCOME = (
    "Olá! Sou o assistente do Life_OS.\n\n"
    "Envie uma mensagem de voz descrevendo algo sobre:\n"
    "• Faculdade (aula, falta, prova…)\n"
    "• Trabalho (tarefa, demanda, deadline…)\n"
    "• Finanças (gasto, receita, investimento…)\n"
    "• Saúde / Nutrição (refeição, macros…)\n\n"
    "Vou extrair as informações e salvar direto no banco. 🎙️"
)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_WELCOME)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pipeline completo: download → LLM → persist → confirm."""
    message = update.message
    voice = message.voice or message.audio

    if voice is None:
        await message.reply_text("Não consegui encontrar o áudio nessa mensagem.")
        return

    await message.reply_chat_action("typing")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".ogg")
    os.close(tmp_fd)

    try:
        tg_file = await context.bot.get_file(voice.file_id)
        await tg_file.download_to_drive(tmp_path)
        logger.info("Áudio baixado: %s", tmp_path)

        # Etapa 1: Motor Cognitivo — STT + extração estruturada
        json_text = await processar_audio_para_json(tmp_path)

        # Etapa 2: Executor — validação de tipos + persistência no banco
        confirmation = await persistir_dados(json_text)

        await message.reply_text(confirmation)

    except ValueError as exc:
        # JSON inválido — dado não estruturável
        logger.error("Dado inválido do Motor Cognitivo: %s", exc)
        await message.reply_text(
            "⚠️ Consegui processar o áudio, mas não entendi os dados. "
            "Tente reformular a mensagem."
        )
    except RuntimeError as exc:
        # Falha no LLM ou no banco
        logger.error("Falha no pipeline de voz: %s", exc)
        await message.reply_text(
            "❌ Não consegui processar o áudio no momento. Tente novamente."
        )
    finally:
        # Executor e LLM Router já removem o arquivo; este guard é safety net.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def main() -> None:
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice)
    )

    logger.info("Life_OS Bot iniciado. Aguardando mensagens...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

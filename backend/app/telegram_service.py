import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self, token: str):
        self.token = token
        # Initialize Bot only if token is provided
        self.bot = Bot(token=self.token) if self.token else None

    async def send_message(self, chat_id: int, message: str) -> bool:
        """
        Asenkron olarak Telegram üzerinden mesaj gönderir.
        """
        if not self.bot:
            logger.warning("Telegram Bot Token bulunamadı. Mesaj gönderilmedi: %s", message)
            return False
            
        try:
            await self.bot.send_message(chat_id=chat_id, text=message)
            return True
        except TelegramError as e:
            logger.error("Telegram mesajı gönderilemedi (Chat ID: %s): %s", chat_id, e)
            return False
        except Exception as e:
            logger.error("Telegram servisinde beklenmeyen hata: %s", e)
            return False

    async def send_document(self, chat_id: int, document_path: str, caption: str = "") -> bool:
        """
        Asenkron olarak Telegram üzerinden belge (PDF vb.) gönderir.
        """
        if not self.bot:
            logger.warning("Telegram Bot Token bulunamadı. Belge gönderilmedi: %s", document_path)
            return False
            
        try:
            with open(document_path, "rb") as doc:
                await self.bot.send_document(chat_id=chat_id, document=doc, caption=caption)
            return True
        except TelegramError as e:
            logger.error("Telegram belgesi gönderilemedi (Chat ID: %s): %s", chat_id, e)
            return False
        except Exception as e:
            logger.error("Telegram servisinde belge gönderilirken beklenmeyen hata: %s", e)
            return False

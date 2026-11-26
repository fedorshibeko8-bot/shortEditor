from aiogram import Bot


class TelegramNotifier:
    def __init__(self, bot: Bot, admin_id: int) -> None:
        self.bot = bot
        self.admin_id = admin_id

    async def send(self, text: str) -> None:
        await self.bot.send_message(self.admin_id, text)

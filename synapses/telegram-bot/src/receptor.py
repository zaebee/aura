import structlog
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from nats_adapter import NatsAdapter
from translator import TelegramTranslator

logger = structlog.get_logger(__name__)


class NegotiationStates(StatesGroup):
    WaitingForBid = State()


class TelegramReceptor:
    """
    Receptor: Handles the 'Synaptic Gap' between Telegram and the Hive.
    Converts external events into Internal Signals and sends them to Core via NATS.
    """

    def __init__(self, adapter: NatsAdapter, translator: TelegramTranslator):
        self.adapter = adapter
        self.translator = translator
        self.router = Router()
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.router.message(Command("start"))(self.cmd_start)
        self.router.message(Command("search"))(self.cmd_search)
        self.router.callback_query(F.data.startswith("select:"))(
            self.process_select_hotel
        )
        self.router.message(
            NegotiationStates.WaitingForBid, F.text.regexp(r"^\d+(\.\d+)?$")
        )(self.process_bid)
        self.router.callback_query(F.data == "pay_stub")(self.process_pay_stub)
        self.router.message(F.photo)(self.process_photo)

    async def cmd_start(self, message: Message) -> None:
        await message.answer(
            "Welcome to Aura! 🤖\n"
            "I can help you find hotels and negotiate the best prices.\n"
            "Use /search <destination> to start."
        )

    async def cmd_search(self, message: Message, command: CommandObject) -> None:
        logger.info(
            "receptor_cmd_search",
            user_id=message.from_user.id if message.from_user else 0,
        )
        # 1. Translate external event to Internal Signal
        signal = self.translator.to_signal(message, command=command)

        # 2. Send Signal to Core via NATS and wait for Observation
        await self.adapter.execute(signal)

    async def process_select_hotel(
        self, callback: CallbackQuery, state: FSMContext
    ) -> None:
        if not callback.data:
            return
        item_id = callback.data.split(":", 1)[1]

        await state.update_data(item_id=item_id)
        await state.set_state(NegotiationStates.WaitingForBid)

        if callback.message:
            await callback.message.answer(
                f"Enter your bid for this item (ID: {item_id}):"
            )
        await callback.answer()

    async def process_bid(self, message: Message, state: FSMContext) -> None:
        data = await state.get_data()

        # 1. Translate external event to Internal Signal
        signal = self.translator.to_signal(message, state_data=data)

        logger.info(
            "receptor_processing_bid",
            user_id=message.from_user.id if message.from_user else 0,
            item_id=data.get("item_id"),
        )

        # 2. Send Signal to Core via NATS and wait for Observation
        observation = await self.adapter.execute(signal)

        if not observation.success:
            await message.answer(f"Sorry, something went wrong: {observation.error}")
            return

        if observation.event_type == "deal_accepted":
            await state.clear()

    async def process_pay_stub(self, callback: CallbackQuery) -> None:
        await callback.answer("Payment functionality coming soon!", show_alert=True)

    async def process_photo(self, message: Message, state: FSMContext) -> None:
        """Handle incoming photos for Perception Chamber."""
        if not message.photo:
            return

        # Get the largest photo
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_path = file.file_path
        if not file_path:
            await message.answer("Failed to download photo.")
            return

        # Download photo
        from io import BytesIO

        result: BytesIO = await message.bot.download_file(file_path)  # type: ignore
        image_bytes = result.read()

        await message.answer("Analyzing image... 👁️")

        data = await state.get_data()
        # 1. Translate photo to Perception Signal
        signal = self.translator.to_signal(
            message, image_bytes=image_bytes, state_data=data
        )

        # 2. Send Signal to Core and wait for Observation (Offer)
        observation = await self.adapter.execute(signal)

        if not observation.success:
            await message.answer(f"Perception failed: {observation.error}")
            return

        # If it was successful, the effector will handle the outgoing event if it's sent via NATS,
        # but since we are using await self.adapter.execute(signal), we get the observation back.
        # NatsAdapter.execute usually returns the observation from the request-reply pattern.

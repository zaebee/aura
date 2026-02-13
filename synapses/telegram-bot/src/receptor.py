import json
from io import BytesIO

import structlog
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aura_core.gen.aura.negotiation.v1 import NegotiateRequest
from grpc_adapter import GrpcAdapter
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

    def __init__(
        self,
        adapter: NatsAdapter,
        translator: TelegramTranslator,
        grpc_adapter: GrpcAdapter | None = None,
    ):
        self.adapter = adapter
        self.grpc_adapter = grpc_adapter
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
        self.router.callback_query(F.data.startswith("list_now:"))(
            self.process_list_now
        )
        self.router.callback_query(F.data.startswith("wrong_specs:"))(
            self.process_wrong_specs
        )

    async def cmd_start(self, message: Message) -> None:
        await message.answer(
            "Welcome to Aura! 🤖\n"
            "I can help you find items and negotiate the best prices.\n"
            "Use /search <query> to start."
        )

    async def cmd_search(self, message: Message, command: CommandObject) -> None:
        logger.info(
            "receptor_cmd_search",
            user_id=message.from_user.id if message.from_user else 0,
        )
        # 1. Translate external event to Internal Signal
        signal = self.translator.to_signal(message, command=command)

        # 2. Send Signal to Core via NATS and wait for Observation
        observation = await self.adapter.execute(signal)

        if observation.success and observation.event_type == "search_results":
             results_raw = observation.metadata.get("item_data", "[]")
             results = json.loads(results_raw)
             if not results:
                 await message.answer("No items found matching your query.")
                 return

             response_text = "🔍 *Search Results:*\n\n"
             keyboard_buttons = []

             for item in results:
                 item_id = item.get("id", "unknown")
                 name = item.get("name", "Unknown Item")
                 price = item.get("base_price", 0.0)

                 response_text += f"• *{name}*\n  Price: ${price}/day\n  ID: `{item_id}`\n\n"
                 keyboard_buttons.append([
                     InlineKeyboardButton(text=f"Select {name}", callback_data=f"select:{item_id}")
                 ])

             await message.answer(
                 response_text,
                 parse_mode="Markdown",
                 reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
             )
        elif not observation.success:
             await message.answer(f"Search failed: {observation.error}")

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

        if observation.event_type in ["deal_accepted", "negotiation_accept"]:
            await state.clear()

    async def process_pay_stub(self, callback: CallbackQuery) -> None:
        await callback.answer("Payment functionality coming soon!", show_alert=True)

    async def process_photo(self, message: Message, state: FSMContext) -> None:
        """Handle incoming photos for Perception Chamber."""
        if not message.photo:
            return

        # Get the lowest resolution photo (as per directive)
        photo = message.photo[0]
        if not message.bot:
            await message.answer("Internal error: bot not initialized.")
            return

        file = await message.bot.get_file(photo.file_id)
        file_path = file.file_path
        if not file_path:
            await message.answer("Failed to download photo.")
            return

        # Download photo
        result: BytesIO = await message.bot.download_file(file_path)  # type: ignore
        image_bytes = result.read()

        await message.answer("Analyzing image... 👁️")

        data = await state.get_data()
        # 1. Translate photo to Perception Signal
        signal = self.translator.to_signal(
            message, image_bytes=image_bytes, state_data=data
        )

        # 2. Send via gRPC Negotiate if available, else fallback to NATS
        if self.grpc_adapter:
            try:
                # Wrap Signal in NegotiateRequest
                req = NegotiateRequest(request_id=signal.identifier, signal=signal)
                response = await self.grpc_adapter.negotiate(req)

                if response.countered:
                    await message.answer(response.countered.human_message)
                elif response.accepted:
                    await message.answer("✅ Deal Accepted!")
                elif response.rejected:
                    await message.answer("❌ Offer Rejected.")
                return
            except Exception as e:
                logger.error("grpc_photo_failed", error=str(e))
                await message.answer(f"gRPC Communication failed: {e}")
                return

        # Fallback to NATS (Legacy/MLS Mode)
        observation = await self.adapter.execute(signal)

        if not observation.success:
            await message.answer(f"Perception failed: {observation.error}")
            return

    async def process_list_now(self, callback: CallbackQuery, state: FSMContext) -> None:
        """Handle 'List Now' confirmation from Vision Report Card."""
        if not callback.data:
            return

        # Translate callback to Signal
        signal = self.translator.to_signal(callback)

        # Execute via NATS
        await self.adapter.execute(signal)

        await callback.answer("Listing request sent! 🚀")
        if isinstance(callback.message, Message):
            # Remove buttons to prevent double-click
            await callback.message.edit_reply_markup(reply_markup=None)

    async def process_wrong_specs(
        self, callback: CallbackQuery, state: FSMContext
    ) -> None:
        """Handle 'Wrong Specs' correction from user (Double Strand Break)."""
        if not callback.data:
            return

        # Translate callback to Signal
        signal = self.translator.to_signal(callback)

        # Execute via NATS
        await self.adapter.execute(signal)

        await callback.answer("Acknowledged. Evolution in progress. 🧬")
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=None)

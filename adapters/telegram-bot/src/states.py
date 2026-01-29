from aiogram.fsm.state import State, StatesGroup


class NegotiationStates(StatesGroup):
    searching = State()
    negotiating = State()

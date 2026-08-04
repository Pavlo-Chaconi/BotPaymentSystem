from aiogram.fsm.state import State, StatesGroup

class RestoreStates(StatesGroup):
    waiting_for_key = State()

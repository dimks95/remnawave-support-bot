from aiogram.fsm.state import State, StatesGroup


class AdminReply(StatesGroup):
    waiting_for_text = State()


class UserNewTicket(StatesGroup):
    waiting_for_text = State()


class AdminFaqEdit(StatesGroup):
    waiting_for_text = State()


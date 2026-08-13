from .models import Conversation, Message, User

#TODO trzeba faktyczną bazę danych + ORM, generalnie obie te klasy niżej do wywalenia

class ConversationStore:

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(self, user_id: str | None = None) -> Conversation:
        conversation = Conversation(user_id=user_id)
        self._conversations[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def add_message(self, conversation_id: str, message: Message) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise KeyError(f"Konwersacja {conversation_id} nie istnieje")

        conversation.messages.append(message)
        return conversation


class UserStore:

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def create(self, username: str) -> User:
        user = User(username=username)
        self._users[user.id] = user
        return user

    def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)


conversations = ConversationStore()
users = UserStore()

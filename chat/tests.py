from django.test import TestCase
from django.contrib.auth.models import User
from documents.models import Document
from .models import Conversation, Message


class ConversationModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

    def test_conversation_str(self):
        convo = Conversation.objects.create(user=self.user, title="Test Convo")
        self.assertEqual(str(convo), "Test Convo")

    def test_conversation_str_no_title(self):
        convo = Conversation.objects.create(user=self.user, title="")
        self.assertIn("Chat", str(convo))


class MessageModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass"
        )
        self.convo = Conversation.objects.create(user=self.user, title="Test")

    def test_message_creation(self):
        msg = Message.objects.create(
            conversation=self.convo, role="user", content="Hello AI"
        )
        self.assertEqual(msg.role, "user")
        self.assertIn("Hello AI", str(msg))

    def test_message_ordering(self):
        msg1 = Message.objects.create(conversation=self.convo, role="user", content="First")
        msg2 = Message.objects.create(conversation=self.convo, role="assistant", content="Second")
        messages = list(Message.objects.filter(conversation=self.convo))
        self.assertEqual(messages[0], msg1)
        self.assertEqual(messages[1], msg2)

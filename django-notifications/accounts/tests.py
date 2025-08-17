from django.test import TestCase
from .models import User

# Run this command to create the test users
# python manage.py test accounts

class UserTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Création de 3 utilisateurs
        cls.user1 = User.objects.create_user(username="admin", email="admin@example.com", password="admin123")
        cls.user2 = User.objects.create_user(username="manager", email="manager@example.com", password="manager123")
        cls.user3 = User.objects.create_user(username="employee", email="employee@example.com", password="employee123")

    def test_users_created(self):
        """Vérifie que les utilisateurs existent bien"""
        self.assertEqual(User.objects.count(), 3)
        self.assertTrue(User.objects.filter(username="admin").exists())
        self.assertTrue(User.objects.filter(username="manager").exists())
        self.assertTrue(User.objects.filter(username="employee").exists())
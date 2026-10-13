"""Autentifikatsiya va rollar testlari."""
from django.test import TestCase
from django.urls import reverse

from .models import User


class RegisterTests(TestCase):
    def test_register_creates_user_with_role(self):
        resp = self.client.post(reverse("register"), {
            "username": "yangi_mijoz",
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "role": "client",
            "password1": "KuchliParol!23",
            "password2": "KuchliParol!23",
        })
        self.assertRedirects(resp, reverse("home"))
        user = User.objects.get(username="yangi_mijoz")
        self.assertEqual(user.role, "client")
        self.assertTrue(user.check_password("KuchliParol!23"))

    def test_register_organizer_role(self):
        resp = self.client.post(reverse("register"), {
            "username": "tashkilotchi1",
            "first_name": "Vali", "last_name": "Aliyev",
            "role": "organizer",
            "password1": "KuchliParol!23", "password2": "KuchliParol!23",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(User.objects.get(username="tashkilotchi1").role, "organizer")

    def test_register_rejects_weak_password(self):
        resp = self.client.post(reverse("register"), {
            "username": "zaif", "first_name": "A", "last_name": "B",
            "role": "client", "password1": "123", "password2": "123",
        })
        self.assertEqual(resp.status_code, 200)  # forma xato bilan qayta ko'rsatiladi
        self.assertFalse(User.objects.filter(username="zaif").exists())

    def test_admin_role_cannot_be_chosen_at_register(self):
        """Ro'yxatdan o'tishda 'admin' rolini tanlab bo'lmasligi kerak."""
        resp = self.client.post(reverse("register"), {
            "username": "hacker", "first_name": "A", "last_name": "B",
            "role": "admin",
            "password1": "KuchliParol!23", "password2": "KuchliParol!23",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="hacker").exists())


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mijoz", password="Parol!2345", role=User.Role.CLIENT
        )

    def test_login_logout(self):
        ok = self.client.login(username="mijoz", password="Parol!2345")
        self.assertTrue(ok)
        self.client.post(reverse("logout"))  # Django 5+ logout faqat POST
        resp = self.client.get(reverse("my_tickets"))
        self.assertEqual(resp.status_code, 302)  # login talab qiladi


class RoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_user = User.objects.create_user(username="c1", password="x", role="client")
        cls.organizer = User.objects.create_user(username="o1", password="x", role="organizer")
        cls.controller = User.objects.create_user(username="k1", password="x", role="controller")
        cls.admin = User.objects.create_user(username="a1", password="x", role="admin")

    def test_client_cannot_access_organizer_dashboard(self):
        self.client.force_login(self.client_user)
        resp = self.client.get(reverse("organizer_dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_client_cannot_access_admin_panel(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

    def test_organizer_cannot_access_admin_panel(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

    def test_controller_cannot_access_organizer_dashboard(self):
        self.client.force_login(self.controller)
        self.assertEqual(self.client.get(reverse("organizer_dashboard")).status_code, 403)

    def test_controller_can_access_scan_page(self):
        self.client.force_login(self.controller)
        self.assertEqual(self.client.get(reverse("scan_page")).status_code, 200)

    def test_client_cannot_access_scan_page(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("scan_page")).status_code, 403)

    def test_admin_can_access_admin_panel(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 200)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("organizer_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

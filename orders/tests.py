"""Sotib olish jarayoni testlari: buyurtma, sig'im, idempotent to'lov, chiptalar."""
import datetime as dt
import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Event, TicketType
from events.tests import make_event

from .models import Order, Ticket, create_tickets_for_order, verify_ticket_token

User = get_user_model()


class PurchaseFlowTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username="org", password="x", role="organizer")
        self.buyer = User.objects.create_user(username="mijoz", password="x", role="client")
        self.event = make_event(self.organizer)
        self.tt = self.event.ticket_types.first()
        self.tt.capacity = 10
        self.tt.price = Decimal("150000")
        self.tt.save()

    def buy(self, qty=2):
        self.client.force_login(self.buyer)
        return self.client.post(
            reverse("order_create", args=[self.event.pk]),
            {"ticket_type": self.tt.pk, "quantity": qty},
        )

    def test_order_created_and_reservation_held(self):
        resp = self.buy(2)
        order = Order.objects.get()
        self.assertRedirects(resp, reverse("order_confirm", args=[order.pk]))
        self.assertEqual(order.status, Order.Status.PENDING)
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.sold, 2)  # o'rin band qilindi

    def test_total_calculated_on_server_ignores_client_price(self):
        """Mijoz yuborgan soxta narx e'tiborga olinmasligi kerak."""
        self.client.force_login(self.buyer)
        self.client.post(
            reverse("order_create", args=[self.event.pk]),
            {"ticket_type": self.tt.pk, "quantity": 3, "price": "1", "total": "3"},
        )
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("450000"))  # 3 × 150 000

    def test_quantity_limits(self):
        resp = self.buy(0)
        self.assertEqual(Order.objects.count(), 0)
        resp = self.buy(11)  # MAX_PER_ORDER=10 dan ko'p
        self.assertEqual(Order.objects.count(), 0)

    def test_cannot_order_more_than_remaining(self):
        self.tt.capacity = 2
        self.tt.sold = 0
        self.tt.save()
        self.buy(3)
        self.assertEqual(Order.objects.count(), 0)
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.sold, 0)

    def test_payment_success_creates_tickets(self):
        self.buy(2)
        order = Order.objects.get()
        resp = self.client.post(reverse("payment_process", args=[order.pk]), {"outcome": "success"})
        self.assertRedirects(resp, reverse("payment_result", args=[order.pk, "success"]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.tickets.count(), 2)
        for t in order.tickets.all():
            self.assertEqual(t.status, Ticket.Status.VALID)
            self.assertTrue(t.serial)
            self.assertTrue(t.qr_token)

    def test_payment_failure_releases_reservation(self):
        self.buy(2)
        order = Order.objects.get()
        self.client.post(reverse("payment_process", args=[order.pk]), {"outcome": "failure"})
        order.refresh_from_db()
        self.tt.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FAILED)
        self.assertEqual(self.tt.sold, 0)  # band qaytarildi
        self.assertEqual(order.tickets.count(), 0)

    def test_repeated_payment_request_is_idempotent(self):
        """Takroriy to'lov so'rovi yangi chiptalar yaratmasligi kerak."""
        self.buy(2)
        order = Order.objects.get()
        self.client.post(reverse("payment_process", args=[order.pk]), {"outcome": "success"})
        first_ids = set(order.tickets.values_list("uid", flat=True))
        # Takroran bir necha marta
        for _ in range(3):
            self.client.post(reverse("payment_process", args=[order.pk]), {"outcome": "success"})
        order.refresh_from_db()
        self.assertEqual(order.tickets.count(), 2)
        self.assertEqual(set(order.tickets.values_list("uid", flat=True)), first_ids)

    def test_cannot_pay_other_users_order(self):
        self.buy(1)
        order = Order.objects.get()
        other = User.objects.create_user(username="begona", password="x", role="client")
        self.client.force_login(other)
        resp = self.client.post(reverse("payment_process", args=[order.pk]), {"outcome": "success"})
        self.assertEqual(resp.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)


class CapacityConcurrencyTests(TransactionTestCase):
    """Bir vaqtda bir nechta mijoz xarid qilganda sig'imdan oshmasligi kerak."""

    def test_no_oversell_under_concurrent_purchases(self):
        organizer = User.objects.create_user(username="org", password="x", role="organizer")
        event = make_event(organizer)
        tt = event.ticket_types.first()
        tt.capacity = 5
        tt.sold = 0
        tt.save()

        results = []
        errors = []
        buyers = []
        for i in range(10):
            buyers.append(User.objects.create_user(username=f"buyer{i}", password="x", role="client"))

        def buy(user):
            from django.db import OperationalError, connection
            from django.test import Client

            last_err = None
            for attempt in range(15):  # SQLite "locked" holatida mijozdek qayta urinish
                try:
                    c = Client()
                    c.force_login(user)
                    resp = c.post(
                        reverse("order_create", args=[event.pk]),
                        {"ticket_type": tt.pk, "quantity": 1},
                    )
                    results.append((user.username, resp.status_code))
                    return
                except Exception as e:  # noqa: BLE001 — vaqtinchalik lock/session poyalari uchun qayta urinish
                    last_err = e
                    import time
                    time.sleep(0.5)
            errors.append((user.username, str(last_err)))
            connection.close()

        threads = [threading.Thread(target=buy, args=(u,)) for u in buyers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertFalse(errors, f"Xatolar: {errors}")
        tt.refresh_from_db()
        self.assertLessEqual(tt.sold, 5, "Sig'imdan ortiq chipta band qilindi!")
        successful = Order.objects.filter(event=event, status=Order.Status.PENDING).count()
        self.assertLessEqual(successful, 5)


class TicketAccessTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username="org", password="x", role="organizer")
        self.owner = User.objects.create_user(username="egasi", password="x", role="client")
        self.other = User.objects.create_user(username="begona", password="x", role="client")
        self.event = make_event(self.organizer)
        tt = self.event.ticket_types.first()

        self.order = Order.objects.create(user=self.owner, event=self.event, status=Order.Status.PAID)
        from .models import OrderItem
        OrderItem.objects.create(order=self.order, ticket_type=tt, quantity=1, unit_price=tt.price)
        self.order.recalc_total()
        self.order.save()
        self.ticket = create_tickets_for_order(self.order)[0]

    def test_owner_can_view_ticket(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("ticket_detail", args=[self.ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.ticket.serial)

    def test_other_user_cannot_view_ticket(self):
        """Boshqa foydalanuvchi chiptani ko'ra/yuklay olmaydi (404 — mavjudlik sir tutiladi)."""
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("ticket_detail", args=[self.ticket.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ticket_pdf", args=[self.ticket.pk])).status_code, 404)

    def test_owner_can_download_pdf(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse("ticket_pdf", args=[self.ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        body = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content
        self.assertTrue(body.startswith(b"%PDF"))
        self.assertGreater(len(body), 500)

    def test_my_tickets_lists_only_own(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse("my_tickets"))
        self.assertNotContains(resp, self.ticket.serial)


class QRTTokenSecurityTests(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username="org", password="x", role="organizer")
        self.buyer = User.objects.create_user(username="mijoz", password="x", role="client", first_name="Maxfiy", last_name="Ma'lumot")

    def test_token_verifies(self):
        ev = make_event(self.organizer)
        order = Order.objects.create(user=self.buyer, event=ev, status=Order.Status.PAID)
        from .models import OrderItem
        OrderItem.objects.create(order=order, ticket_type=ev.ticket_types.first(), quantity=1, unit_price=Decimal("100000"))
        ticket = create_tickets_for_order(order)[0]
        token = ticket.qr_token
        self.assertEqual(verify_ticket_token(token), ticket.uid)

    def test_tampered_token_rejected(self):
        ev = make_event(self.organizer)
        order = Order.objects.create(user=self.buyer, event=ev, status=Order.Status.PAID)
        from .models import OrderItem
        OrderItem.objects.create(order=order, ticket_type=ev.ticket_types.first(), quantity=1, unit_price=Decimal("100000"))
        ticket = create_tickets_for_order(order)[0]
        token = ticket.qr_token
        # Imzoni buzish
        self.assertIsNone(verify_ticket_token(token + "x"))
        self.assertIsNone(verify_ticket_token(token[:-3] + "abc"))
        self.assertIsNone(verify_ticket_token("umuman-boshqa-narsa"))

    def test_token_contains_no_personal_data(self):
        """QR mazmuni faqat imzolangan UUID — parol/shaxsiy ma'lumot yo'q."""
        ev = make_event(self.organizer)
        order = Order.objects.create(user=self.buyer, event=ev, status=Order.Status.PAID)
        from .models import OrderItem
        OrderItem.objects.create(order=order, ticket_type=ev.ticket_types.first(), quantity=1, unit_price=Decimal("100000"))
        ticket = create_tickets_for_order(order)[0]
        token = ticket.qr_token.lower()
        self.assertNotIn("mijoz", token)
        self.assertNotIn("maxfiy", token)
        self.assertNotIn("parol", token)
        self.assertNotIn("password", token)
        # Token qismlari: uuid:imzo — qisqa
        self.assertLess(len(ticket.qr_token), 120)

"""QR nazorat testlari: haqiqiy/noto'g'ri/takroriy kirish, atomarlik."""
import json
import threading

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from checkin.models import ScanLog
from events.tests import make_event
from orders.models import Order, OrderItem, Ticket, create_tickets_for_order

User = get_user_model()


def make_paid_ticket(event, buyer, qty=1):
    tt = event.ticket_types.first()
    order = Order.objects.create(user=buyer, event=event, status=Order.Status.PENDING)
    OrderItem.objects.create(order=order, ticket_type=tt, quantity=qty, unit_price=tt.price)
    tt.sold += qty
    tt.save()
    order.recalc_total()
    order.save()
    return create_tickets_for_order(order)


class VerifyBase(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username="org", password="x", role="organizer")
        self.event = make_event(self.organizer)
        self.buyer = User.objects.create_user(username="mijoz", password="x", role="client")
        self.controller = User.objects.create_user(
            username="nazoratchi", password="x", role="controller"
        )
        self.event.controllers.add(self.controller)
        self.client.force_login(self.controller)

    def verify(self, code, event=None):
        resp = self.client.post(
            reverse("verify_ticket", args=[(event or self.event).pk]),
            data=json.dumps({"code": code}),
            content_type="application/json",
        )
        return resp


class VerifyTicketTests(VerifyBase):
    def test_valid_ticket_grants_entry(self):
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        resp = self.verify(ticket.qr_token)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["result"], "ok")
        self.assertEqual(data["serial"], ticket.serial)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.USED)
        self.assertIsNotNone(ticket.used_at)
        self.assertEqual(ticket.used_by, self.controller)
        # ScanLog yozildi
        log = ScanLog.objects.get(ticket=ticket)
        self.assertEqual(log.result, ScanLog.Result.OK)
        self.assertEqual(log.controller, self.controller)
        self.assertEqual(log.event, self.event)

    def test_second_scan_shows_already_used_with_time(self):
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        self.verify(ticket.qr_token)
        resp = self.verify(ticket.qr_token)
        data = resp.json()
        self.assertEqual(data["result"], "already_used")
        self.assertTrue(data["used_at"], "Oldingi kirish vaqti ko'rsatilishi kerak")
        self.assertEqual(ScanLog.objects.filter(ticket=ticket, result=ScanLog.Result.ALREADY_USED).count(), 1)
        # Har bir urinish qayd etiladi — jami 2 ta log
        self.assertEqual(ScanLog.objects.filter(ticket=ticket).count(), 2)

    def test_tampered_code_rejected(self):
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        resp = self.verify(ticket.qr_token + "buzilgan")
        self.assertEqual(resp.json()["result"], "bad_signature")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.VALID)  # ishlatilmadi

    def test_random_code_not_found(self):
        resp = self.verify("butunlay-tasodifiy-kod")
        self.assertEqual(resp.json()["result"], "bad_signature")

    def test_signed_but_unknown_uuid(self):
        from orders.models import generate_ticket_token
        import uuid
        resp = self.verify(generate_ticket_token(uuid.uuid4()))
        self.assertEqual(resp.json()["result"], "not_found")

    def test_ticket_from_other_event_rejected(self):
        other_event = make_event(self.organizer, title="Boshqa tadbir")
        other_event.controllers.add(self.controller)
        ticket = make_paid_ticket(other_event, self.buyer)[0]
        resp = self.verify(ticket.qr_token, event=self.event)
        data = resp.json()
        self.assertEqual(data["result"], "wrong_event")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.VALID)

    def test_unpaid_order_ticket_rejected(self):
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        ticket.order.status = Order.Status.PENDING
        ticket.order.save()
        resp = self.verify(ticket.qr_token)
        self.assertEqual(resp.json()["result"], "wrong_order")

    def test_cancelled_ticket_rejected(self):
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        ticket.status = Ticket.Status.CANCELLED
        ticket.save()
        resp = self.verify(ticket.qr_token)
        self.assertEqual(resp.json()["result"], "cancelled")

    def test_cancelled_event_ticket_rejected(self):
        from events.models import Event
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        self.event.status = Event.Status.CANCELLED
        self.event.save()
        resp = self.verify(ticket.qr_token)
        self.assertEqual(resp.json()["result"], "cancelled")


class VerifyPermissionsTests(VerifyBase):
    def test_unassigned_controller_forbidden(self):
        stranger = User.objects.create_user(username="begona_n", password="x", role="controller")
        self.client.force_login(stranger)
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        resp = self.verify(ticket.qr_token)
        self.assertEqual(resp.status_code, 403)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.VALID)

    def test_client_cannot_verify(self):
        self.client.force_login(self.buyer)
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        resp = self.client.post(
            reverse("verify_ticket", args=[self.event.pk]),
            data=json.dumps({"code": ticket.qr_token}),
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (302, 403))  # login redirect yoki forbidden
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.VALID)

    def test_organizer_cannot_verify(self):
        self.client.force_login(self.organizer)
        ticket = make_paid_ticket(self.event, self.buyer)[0]
        resp = self.client.post(
            reverse("verify_ticket", args=[self.event.pk]),
            data=json.dumps({"code": ticket.qr_token}),
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (302, 403))


class DoubleScanConcurrencyTests(TransactionTestCase):
    """Ikkita nazoratchi bir vaqtda skanerlasa faqat bittasiga ruxsat beriladi."""

    def test_only_one_controller_gets_ok(self):
        organizer = User.objects.create_user(username="org", password="x", role="organizer")
        event = make_event(organizer)
        buyer = User.objects.create_user(username="mijoz", password="x", role="client")
        c1 = User.objects.create_user(username="naz1", password="x", role="controller")
        c2 = User.objects.create_user(username="naz2", password="x", role="controller")
        event.controllers.add(c1, c2)
        ticket = make_paid_ticket(event, buyer)[0]
        token = ticket.qr_token

        results = []
        errors = []

        def scan(user):
            from django.db import OperationalError, connection
            from django.test import Client

            last_err = None
            for _ in range(15):  # SQLite "locked" holatida qayta urinish
                try:
                    c = Client()
                    c.force_login(user)
                    resp = c.post(
                        reverse("verify_ticket", args=[event.pk]),
                        data=json.dumps({"code": token}),
                        content_type="application/json",
                    )
                    results.append(resp.json()["result"])
                    return
                except Exception as e:  # noqa: BLE001 — vaqtinchalik lock/session poyalari uchun qayta urinish
                    last_err = e
                    import time
                    time.sleep(0.5)
            errors.append(str(last_err))
            connection.close()

        barrier = threading.Barrier(2)

        def scan_synced(user):
            barrier.wait()
            scan(user)

        t1 = threading.Thread(target=scan_synced, args=(c1,))
        t2 = threading.Thread(target=scan_synced, args=(c2,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertFalse(errors, f"Xatolar: {errors}")
        self.assertEqual(len(results), 2)
        self.assertEqual(results.count("ok"), 1, f"Faqat bitta 'ok' kutilgan, natijalar: {results}")
        self.assertEqual(results.count("already_used"), 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.USED)

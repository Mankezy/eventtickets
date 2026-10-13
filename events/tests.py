"""Tadbirlar: qidiruv, filtr, sotuv cheklovlari testlari."""
import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Event, TicketType


def make_event(organizer, title="Konsert", category="music", status="active",
               days_ahead=5, with_types=True):
    ev = Event.objects.create(
        organizer=organizer, title=title, category=category, status=status,
        address="Toshkent, Test ko'chasi 1",
        date=timezone.localdate() + dt.timedelta(days=days_ahead),
        time=dt.time(19, 0),
        description="Test tavsifi",
    )
    if with_types:
        TicketType.objects.create(event=ev, name="Oddiy", price=Decimal("100000"), capacity=10)
    return ev


class EventListTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.organizer = User.objects.create_user(username="org", password="x", role="organizer")

    def test_search_by_title(self):
        make_event(self.organizer, title="Yulduzlar Konserti", category="music")
        make_event(self.organizer, title="Futbol o'yini", category="sport")
        resp = self.client.get(reverse("event_list"), {"q": "yulduz"})
        self.assertContains(resp, "Yulduzlar Konserti")
        self.assertNotContains(resp, "Futbol o'yini")

    def test_filter_by_category(self):
        make_event(self.organizer, title="Konsert A", category="music")
        make_event(self.organizer, title="Match B", category="sport")
        resp = self.client.get(reverse("event_list"), {"category": "sport"})
        self.assertContains(resp, "Match B")
        self.assertNotContains(resp, "Konsert A")

    def test_filter_by_date(self):
        e1 = make_event(self.organizer, title="Bugungi+", days_ahead=3)
        make_event(self.organizer, title="Keyingi", days_ahead=10)
        resp = self.client.get(reverse("event_list"), {"date": e1.date.isoformat()})
        self.assertContains(resp, "Bugungi+")
        self.assertNotContains(resp, "Keyingi")

    def test_cancelled_events_not_listed(self):
        make_event(self.organizer, title="Bekor qilingan kecha", status="cancelled")
        resp = self.client.get(reverse("event_list"))
        self.assertNotContains(resp, "Bekor qilingan kecha")

    def test_empty_state_when_nothing_found(self):
        resp = self.client.get(reverse("event_list"), {"q": "yoq_narsa"})
        self.assertContains(resp, "Hech narsa topilmadi")


class EventSaleRestrictionTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.organizer = User.objects.create_user(username="org", password="x", role="organizer")
        self.client_user = User.objects.create_user(username="mijoz", password="x", role="client")

    def test_cannot_buy_from_cancelled_event(self):
        ev = make_event(self.organizer, status="cancelled")
        tt = ev.ticket_types.first()
        self.client.force_login(self.client_user)
        resp = self.client.post(reverse("order_create", args=[ev.pk]), {
            "ticket_type": tt.pk, "quantity": 1,
        })
        self.assertEqual(resp.status_code, 302)
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)
        tt.refresh_from_db()
        self.assertEqual(tt.sold, 0)

    def test_cannot_buy_from_finished_event(self):
        ev = make_event(self.organizer, status="finished")
        tt = ev.ticket_types.first()
        self.client.force_login(self.client_user)
        self.client.post(reverse("order_create", args=[ev.pk]), {
            "ticket_type": tt.pk, "quantity": 1,
        })
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)

    def test_cannot_buy_past_event(self):
        ev = make_event(self.organizer, days_ahead=-2)
        tt = ev.ticket_types.first()
        self.client.force_login(self.client_user)
        self.client.post(reverse("order_create", args=[ev.pk]), {
            "ticket_type": tt.pk, "quantity": 1,
        })
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)

    def test_detail_page_shows_no_sale_for_cancelled(self):
        ev = make_event(self.organizer, status="cancelled")
        resp = self.client.get(ev.get_absolute_url())
        self.assertContains(resp, "Chipta sotilmaydi")

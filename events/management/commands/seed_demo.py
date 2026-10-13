"""Namunaviy ma'lumotlar yaratish: python manage.py seed_demo"""
import datetime as dt
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from django.utils import timezone
from PIL import Image, ImageDraw

from checkin.models import ScanLog
from events.models import Event, TicketType
from orders.models import Order, Ticket, create_tickets_for_order

User = get_user_model()

PASSWORD = "Test1234!"


def make_event_image(color1, color2, text):
    """Oddiy rangli placeholder rasm yaratish."""
    img = Image.new("RGB", (800, 450), color1)
    draw = ImageDraw.Draw(img)
    for i in range(450):
        t = i / 450
        r = int(color1[0] * (1 - t) + color2[0] * t)
        g = int(color1[1] * (1 - t) + color2[1] * t)
        b = int(color1[2] * (1 - t) + color2[2] * t)
        draw.line([(0, i), (800, i)], fill=(r, g, b))
    draw.text((30, 200), text, fill=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return ContentFile(buf.getvalue())


EVENTS_DATA = [
    {
        "title": "Yulduzlar Konserti 2026",
        "category": Event.Category.MUSIC,
        "description": "O'zbek estradasining yorqin yulduzlari ishtirokida katta konsert dasturi. "
                       "Jonli ijro, maxsus effektlar va unutilmas kecha sizni kutmoqda!",
        "address": "Toshkent sh., Humo Arena, Bunyodkor shohko'chasi 31",
        "days_ahead": 14,
        "time": "19:00",
        "colors": ((94, 53, 177), (236, 64, 122), "YULDUZLAR KONSERTI"),
        "types": [("Oddiy", "150000", 200), ("VIP", "400000", 50)],
    },
    {
        "title": "Paxtakor — Bunyodkor",
        "category": Event.Category.SPORT,
        "description": "O'zbekiston Superligasi doirasidagi markaziy uchrashuv. "
                       "Jamoaingizni stadionda qo'llab-quvvatlang!",
        "address": "Toshkent sh., Paxtakor markaziy stadioni, Mustaqillik shohko'chasi",
        "days_ahead": 7,
        "time": "17:30",
        "colors": ((30, 100, 40), (20, 60, 120), "PAXTAKOR - BUNYODKOR"),
        "types": [("Oddiy", "80000", 300), ("VIP", "250000", 40)],
    },
    {
        "title": "IT Conference Toshkent",
        "category": Event.Category.CONFERENCE,
        "description": "Dasturlash, sun'iy intellekt va startaplar haqida zamonaviy konferensiya. "
                       "20+ ma'ruzachi, amaliy workshoplar va networking.",
        "address": "Toshkent sh., Xalqaro biznes markazi, Amir Temur ko'chasi 1",
        "days_ahead": 21,
        "time": "10:00",
        "colors": ((33, 37, 41), (88, 28, 135), "IT CONFERENCE"),
        "types": [("Standart", "300000", 150), ("VIP", "700000", 30)],
    },
    {
        "title": "Milliy Teatr: O'tkan kunlar",
        "category": Event.Category.THEATER,
        "description": "Abdulla Qodiriyning mashhur romani asosidagi spektakl. "
                       "Milliy teatr sahnasida yangicha talqinda.",
        "address": "Toshkent sh., Milliy akademik drama teatri, Zarqaynar ko'chasi 19",
        "days_ahead": 10,
        "time": "18:30",
        "colors": ((120, 20, 20), (60, 20, 80), "O'TKAN KUNLAR"),
        "types": [("Oddiy", "120000", 120), ("VIP", "300000", 25)],
    },
    {
        "title": "Navro'z Fest",
        "category": Event.Category.FESTIVAL,
        "description": "Navro'z bayramiga bag'ishlangan open-air festival: "
                       "milliy taomlar, hunarmandlar yarmarkasi va konsert dasturi.",
        "address": "Samarqand sh., Registon maydoni",
        "days_ahead": 30,
        "time": "11:00",
        "colors": ((0, 120, 100), (200, 150, 20), "NAVRUZ FEST"),
        "types": [("Kirish", "50000", 500), ("VIP", "150000", 80)],
    },
]


class Command(BaseCommand):
    help = "Namunaviy tadbirlar va sinov akkauntlarini yaratadi"

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Avval eski ma'lumotlarni o'chirish")

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Eski ma'lumotlar o'chirilmoqda...")
            ScanLog.objects.all().delete()
            Ticket.objects.all().delete()
            Order.objects.all().delete()
            TicketType.objects.all().delete()
            Event.objects.all().delete()

        # --- Foydalanuvchilar ---
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True,
                "first_name": "Tizim", "last_name": "Administratori",
                "email": "admin@example.com",
            },
        )
        admin_user.set_password(PASSWORD)
        admin_user.save()

        organizer, _ = User.objects.get_or_create(
            username="organizer",
            defaults={
                "role": User.Role.ORGANIZER, "first_name": "Aziz",
                "last_name": "Tashkilotchi", "email": "organizer@example.com",
            },
        )
        organizer.set_password(PASSWORD)
        organizer.save()

        organizer2, _ = User.objects.get_or_create(
            username="organizer2",
            defaults={
                "role": User.Role.ORGANIZER, "first_name": "Dilnoza",
                "last_name": "Karimova", "email": "organizer2@example.com",
            },
        )
        organizer2.set_password(PASSWORD)
        organizer2.save()

        controller, _ = User.objects.get_or_create(
            username="controller",
            defaults={
                "role": User.Role.CONTROLLER, "first_name": "Jasur",
                "last_name": "Nazoratchi", "email": "controller@example.com",
            },
        )
        controller.set_password(PASSWORD)
        controller.save()

        client, _ = User.objects.get_or_create(
            username="client",
            defaults={
                "role": User.Role.CLIENT, "first_name": "Malika",
                "last_name": "Mijoz", "email": "client@example.com",
            },
        )
        client.set_password(PASSWORD)
        client.save()

        self.stdout.write(self.style.SUCCESS("[OK] Sinov akkauntlari tayyor (parol: %s)" % PASSWORD))

        # --- Tadbirlar ---
        today = timezone.localdate()
        created_events = []
        for i, data in enumerate(EVENTS_DATA):
            event, created = Event.objects.get_or_create(
                title=data["title"],
                defaults={
                    "organizer": organizer if i % 2 == 0 else organizer2,
                    "category": data["category"],
                    "description": data["description"],
                    "address": data["address"],
                    "date": today + dt.timedelta(days=data["days_ahead"]),
                    "time": dt.datetime.strptime(data["time"], "%H:%M").time(),
                    "status": Event.Status.ACTIVE,
                },
            )
            if not event.image:
                c1, c2, text = data["colors"]
                try:
                    event.image.save(
                        f"event_{event.pk}.jpg",
                        make_event_image(c1, c2, text),
                        save=False,
                    )
                except Exception as e:  # rasm ixtiyoriy
                    self.stdout.write(self.style.WARNING(f"Rasm yaratilmadi: {e}"))
            event.save()
            # Nazoratchini biriktirish
            event.controllers.add(controller)

            for name, price, capacity in data["types"]:
                TicketType.objects.get_or_create(
                    event=event, name=name,
                    defaults={"price": Decimal(price), "capacity": capacity},
                )
            created_events.append(event)

        # Bitta bekor qilingan va bitta tugagan tadbir (chegara holatlarini tekshirish uchun)
        cancelled, _ = Event.objects.get_or_create(
            title="Bekor qilingan kecha",
            defaults={
                "organizer": organizer,
                "category": Event.Category.MUSIC,
                "description": "Bu tadbir tashkilotchi tomonidan bekor qilingan — chipta sotilmaydi.",
                "address": "Toshkent sh., Kongress xoll",
                "date": today + dt.timedelta(days=5),
                "time": "19:00",
                "status": Event.Status.CANCELLED,
            },
        )
        TicketType.objects.get_or_create(
            event=cancelled, name="Oddiy",
            defaults={"price": Decimal("100000"), "capacity": 50},
        )

        # --- Demo buyurtma: mijoz allaqachon 2 ta chipta sotib olgan ---
        first_event = created_events[0]
        vip_type = first_event.ticket_types.get(name="VIP")
        if not Order.objects.filter(user=client, event=first_event, status=Order.Status.PAID).exists():
            order = Order.objects.create(
                user=client, event=first_event, status=Order.Status.PENDING
            )
            from orders.models import OrderItem

            OrderItem.objects.create(
                order=order, ticket_type=vip_type, quantity=2, unit_price=vip_type.price
            )
            order.recalc_total()
            order.save()
            vip_type.sold += 2
            vip_type.save()
            create_tickets_for_order(order)
            self.stdout.write(self.style.SUCCESS("[OK] Demo buyurtma va 2 ta chipta yaratildi"))

        self.stdout.write(self.style.SUCCESS(
            "[OK] Namunaviy ma'lumotlar tayyor!\n"
            "  Akkauntlar: admin / organizer / organizer2 / controller / client\n"
            f"  Parol (hammasi uchun): {PASSWORD}\n"
            f"  Tadbirlar soni: {Event.objects.count()}"
        ))

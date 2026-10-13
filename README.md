# Tadbirlar uchun chipta sotish va QR nazorat

Django asosida yaratilgan to'liq ishlaydigan veb-ilova: tadbirlarga chipta sotish, DEMO to'lov, QR-chipta generatsiyasi va QR orqali kirishni nazorat qilish.

## Texnologiyalar

- Python 3.11+ / Django 5
- Django shablonlari + Bootstrap 5 + JavaScript (jsQR orqali kamera skaneri)
- SQLite (fayl asosidagi baza, qo'shimcha serversiz)
- qrcode, reportlab (PDF chipta), python-dotenv

## Rollar

| Rol | Imkoniyatlari |
|---|---|
| Mijoz (client) | Ro'yxatdan o'tish, tadbirlarni ko'rish, chipta sotib olish, "Mening chiptalarim"da ko'rish/yuklab olish |
| Tashkilotchi (organizer) | O'z tadbirlarini yaratish/tahrirlash, chipta turlarini belgilash, sotuv natijalarini ko'rish |
| Nazoratchi (controller) | O'ziga biriktirilgan tadbirlarda QR skanerlash, kirishni tasdiqlash |
| Administrator (admin) | Barcha tadbirlar, foydalanuvchilar va buyurtmalarni boshqarish |

Barcha ruxsatlar **backendda** (`accounts/decorators.py` dagi `role_required`) tekshiriladi — frontend faqat tugmalarni yashirish uchun ishlatiladi.

## O'rnatish va ishga tushirish (ketma-ket)

Loyiha papkasida terminal oching va quyidagi buyruqlarni **ketma-ket** bajaring:

```bash
# 1. Virtual muhit (tavsiya etiladi)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Kerakli kutubxonalarni o'rnatish
pip install -r requirements.txt

# 3. .env faylini yaratish (maxfiy kalitlar kodga yozilmagan!)
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux

# 4. Bazani tayyorlash
python manage.py migrate

# 5. Namunaviy ma'lumotlarni yuklash (tadbirlar, test foydalanuvchilar)
python manage.py seed_demo

# 6. Serverni ishga tushirish
python manage.py runserver
```

Brauzerda oching: **http://127.0.0.1:8000/**

> Agar oldin yuklangan ma'lumotlarni tozalab qaytadan yuklamoqchi bo'lsangiz: `python manage.py seed_demo --flush`

## Test hisoblar (parol hammasida bir xil: `Test1234!`)

| Login | Rol |
|---|---|
| `admin` | Administrator |
| `organizer` | Tashkilotchi |
| `organizer2` | Tashkilotchi (ikkinchi) |
| `controller` | Nazoratchi |
| `client` | Mijoz |

Login sahifasida bu hisoblar eslatma sifatida ko'rsatiladi.

## Asosiy oqimlarni qo'lda sinab ko'rish

1. **Mijoz sifatida xarid**: `client` bilan kiring → bosh sahifada tadbirni tanlang → chipta turi va sonini kiriting → "Buyurtma" → to'lov sahifasida **"DEMO TO'LOV"** blokidagi muvaffaqiyatli/muvaffaqiyatsiz tugmani bosing → natija sahifasini ko'ring → "Mening chiptalarim"da QR-chiptani ochib PDF yuklab oling.
2. **Nazoratchi sifatida QR tekshirish**: `controller` bilan kiring → "QR nazorat" sahifasiga o'ting → kamerani yoqing yoki kodni qo'lda kiritib yuboring → natija rangini kuzating (yashil — kirish berildi, sariq — avval ishlatilgan, qizil — xato/notogri).
3. **Tashkilotchi sifatida**: `organizer` bilan kiring → "Tashkilotchi" panelidan yangi tadbir yaratish, chipta turlarini qo'shish, sotuv statistikasini ko'rish.
4. **Administrator sifatida**: `admin` bilan kiring → "Admin panel"dan barcha tadbir/foydalanuvchi/buyurtmalarni ko'rish va boshqarish.

## Testlarni ishga tushirish

```bash
python manage.py test
```

51 ta test mavjud: autentifikatsiya, rollarga ruxsat, qidiruv/filtr, sotilmaydigan tadbirlar, server tomonidan narx hisoblash, bir vaqtda bir nechta xaridorda sig'imdan oshmaslik (concurrency), takroriy to'lov so'rovining xavfsizligi (idempotentlik), chiptaga faqat egasining kirishi, QR token xavfsizligi va bir vaqtda ikki nazoratchi skanerlasa faqat bittasiga ruxsat berilishi tekshiriladi.

## Render'ga joylash

Loyiha Render uchun tayyorlangan: `render.yaml`, `build.sh`, `start.sh`, `gunicorn`, `whitenoise` va `DATABASE_URL` qo'llovi bor.

Eng oson yo'l:

1. Loyihani GitHub repository'ga push qiling.
2. Render.com → **New +** → **Blueprint** yoki **Web Service** tanlang.
3. GitHub repository'ni ulang.
4. Agar Blueprint tanlasangiz, Render `render.yaml` faylini o'zi o'qiydi.
5. Deploy tugagandan keyin sayt `https://...onrender.com` domenida ochiladi.

Render start paytida avtomatik bajariladi:

```bash
python manage.py migrate --noinput
python manage.py seed_demo
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Render muhit o'zgaruvchilari:

| Kalit | Qiymat |
|---|---|
| `SECRET_KEY` | Render avtomatik generate qiladi |
| `DEBUG` | `0` |
| `ALLOWED_HOSTS` | `*` yoki aniq Render domeni |
| `SERVE_LOCAL_MEDIA` | `1` demo uchun |
| `CSRF_TRUSTED_ORIGINS` | `https://*.onrender.com` yoki aniq domen |
| `DATABASE_URL` | ixtiyoriy PostgreSQL URL; bo'lmasa SQLite ishlaydi |

## Loyihaning cheklovlari (halol ogohlantirish)

- To'lov **faqat DEMO rejimida** ishlaydi — haqiqiy bank/karta integratsiyasi yo'q va so'ralmaydi.
- Baza lokal va oddiy Render demo holatida SQLite. Juda yuqori yuklama yoki Render qayta deploy/restart holatlarida doimiy production baza uchun PostgreSQL ulash tavsiya etiladi.
- Render demo uchun media fayllar Django orqali beriladi (`SERVE_LOCAL_MEDIA=1`). Katta production loyiha uchun S3/Cloudinary kabi tashqi storage ishlatish yaxshiroq.
- Email orqali tasdiqlash yoki parolni unutish funksiyasi hali yo'q.
- Media fayllar (tadbir rasmlari) demo rejimida PIL orqali avtomatik generatsiya qilinadi — haqiqiy fayl yuklash funksiyasi tadbir yaratish/tahrirlash shaklida mavjud.

## Papka tuzilishi

```
eventtickets/
  accounts/   - foydalanuvchi modeli, rol, ro'yxatdan o'tish/login
  events/     - tadbir va chipta turi modellari, ro'yxat/filtr, tashkilotchi va admin panellari
  orders/     - buyurtma, to'lov (DEMO), chipta, QR token, PDF
  checkin/    - QR skanerlash va kirish nazorati, ScanLog
  templates/  - Bootstrap asosidagi o'zbek tilidagi shablonlar
  static/     - CSS (purple tema) va JS (skaner, UI)
```

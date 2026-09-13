# AGENTS.md

## Project Overview
QR-code restaurant ordering system. Customers scan a table's QR code to browse menu, order, and pay. Kitchen staff sees orders in real-time on a dashboard.

- **Framework:** Django 5.0.6, Python 3.12.4
- **Database:** PostgreSQL (Supabase) via `dj-database-url`
- **Media:** Cloudinary (`django-cloudinary-storage`)
- **Static files:** WhiteNoise
- **Deployed at:** `speedyorder.onrender.com`

## Project Structure

```
orderingres/       # Django project config (settings, urls, wsgi/asgi)
resturant/         # Main app: models, views, urls (note: "resturant" is intentional typo, do NOT rename)
Templates/         # HTML templates (note capital T, not inside an app)
static/            # Static assets (images only so far)
```

## Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python manage.py runserver

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser (for admin/kitchen access)
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic
```

## Environment Variables (`.env`)

```
DATABASE_URL=...        # PostgreSQL connection string (Supabase)
SECRET_KEY=...          # Django secret key
DEBUG=True|False        # Must be string "True" to enable
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

`DEBUG` defaults to `False`. Set `DEBUG=True` in `.env` for local dev.

## URL Routing

All routes live in `resturant/urls.py`, included at root via `orderingres/urls.py`.

**Customer-facing** (slug + UUID QR token based, e.g. `/my-restaurant-slug/<uuid>/`). `<slug>` is the `Restaurant.slug`, `<uuid>` is the `Table.qr_token` — the slug differentiates restaurants on shared domains:
- `/<slug>/<uuid>/` — Menu browsing
- `/<slug>/<uuid>/cart/` — Cart view/add
- `/<slug>/<uuid>/cart/send/` — Submit order
- `/<slug>/<uuid>/orderstatus/` — Order tracking (AJAX polling at `/refresh/`)
- `/<slug>/<uuid>/checkout/` — Payment checkout
- `/<slug>/<uuid>/request-bill/` — Request bill
- `/<slug>/<uuid>/help/` — Helpdesk

The legacy `/t/<uuid>/...` routes were removed; do not reference them.

**Kitchen/staff** (login required):
- `/kitchen/login/` — Staff login
- `/kitchen/dashboard/` — Kitchen ticket board
- `/kitchen/display/` — Kitchen display (served orders filtered out)
- `/kitchen/order/<id>/status/` — Advance order status (pending→preparing→ready→served)
- `/kitchen/table/<id>/mark-ready/` — Mark all preparing orders for a table as ready
- `/dashboard/` — Management analytics dashboard

## Models (Key Relationships)

- `Table` → has `qr_token` (UUID), used in all customer URLs
- `TableSession` → links to Table, tracks ordering state (`ordering` → `awaiting_payment` → `closed`)
- `CartItem` → belongs to a TableSession, holds items before order submission
- `Order` → created from cart, status lifecycle: `pending` → `preparing` → `ready` → `served`
- `OrderItem` → snapshot of price at order time (`price_at_order`)
- `Bill` → OneToOne with TableSession, Paystack reference

## Important Details

- **Template directory** is `Templates/` (capital T) at project root, not inside the app. Configured in `settings.py`.
- **Table sessions** are created lazily in `resturant/utils.py:get_active_session()` — no explicit creation endpoint.
- **Rate limiting** is applied via `django-ratelimit` on most views. Kitchen status updates use `block=False` with manual check via `request.limited`.
- **No test suite exists** — `resturant/tests.py` is empty. There are no CI test steps.
- **CI** (`.github/workflows/django.yml`) — check the file for actual workflow steps.
- **No linter or formatter** is configured in the repo.
- **`.gitignore`** only ignores `.env`. No other ignores are set.

## Gotchas

- The app directory is `resturant/` (misspelling of "restaurant") — do not rename, it will break imports and migrations.
- `requirements.txt` has duplicate entries (appears to be a concatenation of two pip freeze outputs). Dependencies may include unused packages (Scrapy, yt-dlp, tweepy).
- `ALLOWED_HOSTS` is defined twice in `settings.py` (second overwrites first, both identical).
- Kitchen session expiry is hardcoded to `12390` seconds (~3.4 hours) in `views.py:207`.
- `mark_table_orders_ready` marks preparing orders as ready and keeps them (orders are hidden from the kitchen live board via `.exclude(status__in=["ready","served"])` so they don't clutter the ticket view, but they remain in the DB for billing and customer history).
- Template filenames contain spaces (e.g., `request bill.html`) — reference them exactly as named.

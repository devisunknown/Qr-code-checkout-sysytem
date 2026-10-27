from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse

from django.db import transaction
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .models import (
    Bill,
    CartItem,
    Category,
    MenuItem,
    Order,
    OrderItem,
    Restaurant,
    Table,
    TableSession,
)
from .utils import get_active_session, get_dashboard_restaurant, restaurant_required


@ratelimit(key='user_or_ip', rate='5/m', method='POST', block=True)
def index(request, restaurant_slug, qr_token):
    table, session = get_active_session(restaurant_slug, qr_token)
    query = request.GET.get("q", "").strip()

    menu_items = MenuItem.objects.filter(restaurant=table.restaurant, is_available=True).select_related("category")
    if query:
        menu_items = menu_items.filter(name__icontains=query)

    categories = Category.objects.filter(restaurant=table.restaurant)
    cart_items = session.cart_items.select_related("menu_item")
    cart_count = sum(item.quantity for item in cart_items)
    cart_total = sum(item.menu_item.price * item.quantity for item in cart_items)
    return render(request, 'index.html', {
        "table": table,
        "session": session,
        "menu_items": menu_items,
        "categories": categories,
        "cart_count": cart_count,
        "cart_total": cart_total,
        "query": query,
    })

@ratelimit(key='user_or_ip', rate='5/m', method='POST', block=True)
def cart(request, restaurant_slug, qr_token):
    table, session = get_active_session(restaurant_slug, qr_token)

    if request.method == "POST":
        menu_item_id = request.POST.get("menu_item_id")
        if menu_item_id:
            menu_item = get_object_or_404(MenuItem, id=menu_item_id, restaurant=table.restaurant)
            quantity = int(request.POST.get("quantity", 1) or 1)
            if not menu_item.is_available or (menu_item.is_stock_tracked and menu_item.stock_quantity < quantity):
                messages.error(request, f"Sorry, {menu_item.name} is sold out or not in stock.")
            elif quantity > 0:
                cart_item, created = CartItem.objects.get_or_create(
                    table_session=session,
                    menu_item=menu_item,
                    defaults={"quantity": quantity},
                )
                if not created:
                    cart_item.quantity += quantity
                    cart_item.save()
                messages.success(request, f"{menu_item.name} added to your cart")
            else:
                messages.error(request, "Please choose a valid quantity")
        return redirect("table_cart", restaurant_slug=restaurant_slug, qr_token=qr_token)

    items = session.cart_items.select_related("menu_item")
    # Attach line_total to each cart item for template use
    for item in items:
        item.line_total = item.menu_item.price * item.quantity
    total = sum(item.menu_item.price * item.quantity for item in items)
    return render(request, 'cart.html', {"table": table, "session": session, "items": items, "total": total})


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
def orderstatus(request, restaurant_slug, qr_token):
    table, session = get_active_session(restaurant_slug, qr_token)
    orders = session.orders.prefetch_related("items__menu_item")
    return render(request, 'orderstatus.html', {"table": table, "session": session, "orders": orders})


@ratelimit(key='user_or_ip', rate='120/m', method='GET', block=True)
def orderstatus_refresh(request, restaurant_slug, qr_token):
    """Returns just the order timeline HTML fragment, for AJAX polling on the
    order status page. Renders the exact same partial/context as the full
    page view, so there is a single source of truth for the markup."""
    table, session = get_active_session(restaurant_slug, qr_token)
    orders = session.orders.prefetch_related("items__menu_item")
    all_served = orders.exists() and not orders.exclude(status="served").exists()
    html = render_to_string('partials/order_timeline.html', {
        "table": table,
        "session": session,
        "orders": orders,
    }, request=request)
    response = HttpResponse(html, content_type="text/html")
    response["X-All-Served"] = "1" if all_served else "0"
    return response


@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=True)
def request_bill(request, restaurant_slug, qr_token):
    table, session = get_active_session(restaurant_slug, qr_token)
    orders = session.orders.exclude(status='served')

    if request.method == "POST" and orders.exists():
        orders.update(bill_requested=True)
        messages.info(request, "Bill requested successfully. Your server has been notified.")

    if orders.exists():
        items = list(OrderItem.objects.filter(order__in=orders).select_related("menu_item"))
        for item in items:
            item.line_total = item.price_at_order * item.quantity
        total = sum(item.line_total for item in items)

        order = orders.order_by('-placed_at').first()
    else:
        order = None
        items = list(session.cart_items.select_related("menu_item"))
        for item in items:
            item.line_total = item.menu_item.price * item.quantity
        total = sum(item.line_total for item in items)

    return render(request, 'request bill.html', {
        "table": table,
        "session": session,
        "order": order,
        "items": items,
        "total": total,
    })


@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=True)
@require_POST
def cart_update(request, restaurant_slug, qr_token, item_id):
    table, session = get_active_session(restaurant_slug, qr_token)
    cart_item = get_object_or_404(CartItem, id=item_id, table_session=session)

    quantity = request.POST.get("quantity")
    try:
        new_quantity = int(quantity)
    except (TypeError, ValueError):
        new_quantity = cart_item.quantity

    notes = request.POST.get("notes")
    if notes is not None:
        cart_item.notes = notes.strip()[:255]

    if new_quantity <= 0:
        cart_item.delete()
    else:
        cart_item.quantity = new_quantity
        cart_item.save()

    return redirect("table_cart", restaurant_slug=restaurant_slug, qr_token=qr_token)


@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=True)
@require_POST
def cart_remove(request, restaurant_slug, qr_token, item_id):
    table, session = get_active_session(restaurant_slug, qr_token)
    cart_item = get_object_or_404(CartItem, id=item_id, table_session=session)
    cart_item.delete()
    return redirect("table_cart", restaurant_slug=restaurant_slug, qr_token=qr_token)


@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=True)
@require_POST
def cart_send(request, restaurant_slug, qr_token):
    table, session = get_active_session(restaurant_slug, qr_token)
    items = list(session.cart_items.select_related("menu_item"))

    if items:
        # Reject the whole submission if anything went out of stock since it
        # was added to the cart — partial orders are worse than none.
        unavailable = [
            item.menu_item.name for item in items
            if not item.menu_item.is_available or (
                item.menu_item.is_stock_tracked
                and item.menu_item.stock_quantity < item.quantity
            )
        ]
        if unavailable:
            messages.error(request, "Sorry, the following just sold out: " + ", ".join(unavailable) + ". Please adjust your cart.")
            return redirect("table_cart", restaurant_slug=restaurant_slug, qr_token=qr_token)

        with transaction.atomic():
            order = Order.objects.create(table_session=session, status="pending")
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    menu_item=item.menu_item,
                    quantity=item.quantity,
                    price_at_order=item.menu_item.price,
                    notes=item.notes,
                )
                for item in items
            ])
            low_stock_names = []
            for item in items:
                if item.menu_item.decrement_stock(item.quantity) == "low" and item.menu_item.stock_status == "low":
                    low_stock_names.append(item.menu_item.name)
            session.cart_items.all().delete()
            session.status = "awaiting_payment"
            session.save(update_fields=["status"])
        if low_stock_names:
            messages.info(request, "Heads up: low stock remaining for " + ", ".join(low_stock_names) + ".")
        return redirect("orderstatus", restaurant_slug=restaurant_slug, qr_token=qr_token)

    return redirect("table_cart", restaurant_slug=restaurant_slug, qr_token=qr_token)


def _legacy_restaurant_slug(request):
    """Best-effort restaurant slug for the legacy (non slug-scoped) staff URLs."""
    user = request.user
    if user.is_authenticated and not user.is_superuser and user.restaurant_id:
        return user.restaurant.slug
    restaurant = Restaurant.objects.filter(is_active=True).first()
    return restaurant.slug if restaurant else None


@ratelimit(key='user_or_ip', rate='5/m', method='POST', block=True)
def kitchenlogin(request, restaurant_slug):
    restaurant = get_object_or_404(Restaurant, slug=restaurant_slug, is_active=True)
    request.restaurant = restaurant
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            request.session.set_expiry(12390)
            messages.success(request, 'user is authenticated')
            if not user.is_superuser and user.restaurant_id:
                target_slug = user.restaurant.slug
            else:
                target_slug = restaurant.slug
            return redirect('kitchendashboard', restaurant_slug=target_slug)
        else:
            messages.error(request, 'user not authenticated')
            return redirect('kitchenlogin', restaurant_slug=restaurant_slug)

    return render(request, 'kitchenlogin.html', {"restaurant": restaurant})


@require_POST
def kitchenlogout(request, restaurant_slug=None):
    slug = _legacy_restaurant_slug(request)
    logout(request)
    messages.success(request, 'You have been logged out.')
    if slug:
        return redirect('kitchenlogin', restaurant_slug=slug)
    return redirect('legacy_kitchen_login')


def legacy_kitchen_login(request):
    """Send legacy /kitchen/login/ visitors to their restaurant's login page."""
    slug = _legacy_restaurant_slug(request)
    if slug:
        return redirect('kitchenlogin', restaurant_slug=slug)
    return render(request, 'kitchenlogin.html', {"restaurant": None})


def _make_legacy_redirect(route_name):
    """Build a view that redirects a legacy staff URL to its slug-scoped route."""
    def _view(request, *args, **kwargs):
        slug = _legacy_restaurant_slug(request)
        if slug:
            kwargs['restaurant_slug'] = slug
            return redirect(route_name, **kwargs)
        return redirect('legacy_kitchen_login')

    _view.__name__ = f"legacy_{route_name}"
    return _view


legacy_kitchen_dashboard = _make_legacy_redirect('kitchendashboard')
legacy_kitchen_display = _make_legacy_redirect('kitchendisplay')
legacy_kitchen_displaywidget = _make_legacy_redirect('kitchendisplaywidget')
legacy_advance_order_status = _make_legacy_redirect('advance_order_status')
legacy_mark_table_orders_ready = _make_legacy_redirect('mark_table_orders_ready')
legacy_management_dashboard = _make_legacy_redirect('dashboard')
legacy_close_table_session = _make_legacy_redirect('close_table_session')


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def dashboard(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    orders = (Order.objects
                  .filter(
                      table_session__status__in=["ordering", "awaiting_payment"],
                      table_session__restaurant=restaurant,
                  )
                  .exclude(status__in=["ready", "served"])
                  .select_related("table_session__table")
                  .prefetch_related("items__menu_item")
                  .order_by("placed_at"))
    live_ticket_count = orders.exclude(status="served").count()
    tables_active = orders.values('table_session__table').distinct().count()
    tables_with_bill_request = set(
        orders.filter(bill_requested=True).values_list('table_session__table_id', flat=True)
    )
    restaurants = None
    if request.user.is_superuser:
        restaurants = Restaurant.objects.filter(is_active=True).order_by("name")
        if restaurant is None:
            messages.info(request, "No active restaurants yet. Add one in the admin to get started.")
    return render(request, 'kitchendashboard.html', {
        "orders": orders,
        "live_ticket_count": live_ticket_count,
        "tables_active": tables_active,
        "tables_with_bill_request": tables_with_bill_request,
        "restaurant": restaurant,
        "restaurants": restaurants,
        "selected_restaurant": restaurant,
    })

VALID_ORDER_STATUSES = {"pending", "preparing", "ready", "served"}

@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=False)
@restaurant_required
@require_POST
def advance_order_status(request, order_id, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    if getattr(request, 'limited', False):
        messages.error(request, "You're updating tickets too quickly — please wait a moment and try again.")
        return redirect("kitchendashboard", restaurant_slug=restaurant.slug)

    order = get_object_or_404(Order, id=order_id, table_session__restaurant=restaurant)
    new_status = request.POST.get("status")

    if new_status not in VALID_ORDER_STATUSES:
        messages.error(request, "Invalid status update.")
        return redirect("kitchendashboard", restaurant_slug=restaurant.slug)

    order.status = new_status
    if new_status == "preparing":
        order.started_preparing_at = timezone.now()
    order.save()

    messages.success(request, f"Order #{order.id} marked as {order.get_status_display()}.")
    return redirect("kitchendashboard", restaurant_slug=restaurant.slug)

@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def kitchendisplay(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    orders = (Order.objects
              .filter(
                  table_session__restaurant=restaurant
              )
              .exclude(status="served")
              .select_related("table_session__table")
              .prefetch_related("items__menu_item")
              .order_by("placed_at"))
    return render(request, 'kitchendisplay.html', {
        "orders": orders,
        "live_ticket_count": orders.count(),
        "tables_active": TableSession.objects.filter(status__in=["ordering", "awaiting_payment"], restaurant=restaurant).count(),
        "restaurant": restaurant,
    })


@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=True)
@restaurant_required
@require_POST
def mark_table_orders_ready(request, table_id, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    try:
        table = get_object_or_404(Table, id=table_id, restaurant=restaurant)

        updated = Order.objects.filter(
            table_session__table_id=table.id,
            table_session__restaurant=restaurant,
            status='preparing',
        ).update(status='ready')

        ready_orders = Order.objects.filter(
            table_session__table_id=table.id,
            table_session__restaurant=restaurant,
            status='ready',
        )
        if ready_orders.exists():
            messages.success(
                request,
                f'{ready_orders.count()} order(s) for table marked as ready. Customers will be notified.'
            )
        else:
            messages.info(request, 'No preparing orders found for this table.')
    except Exception as e:
        messages.error(request, f'An error occurred while marking orders as ready: {str(e)}')
    return redirect('kitchendashboard', restaurant_slug=restaurant.slug)


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def kitchendisplaywidget(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    orders = (Order.objects
              .filter(
                  table_session__restaurant=restaurant
              )
              .exclude(status="served")
              .select_related("table_session__table")
              .prefetch_related("items__menu_item")
              .order_by("placed_at"))
    return render(request, 'kitchendisplaywidget.html', {
        "orders": orders,
        "live_ticket_count": orders.count(),
        "tables_active": TableSession.objects.filter(status__in=["ordering", "awaiting_payment"], restaurant=restaurant).count(),
        "restaurant": restaurant,
    })
@ratelimit(key='user_or_ip', rate='5/m', method='GET', block=True)
def helpdesk(request, restaurant_slug, qr_token):
    table, session = get_active_session(restaurant_slug, qr_token)
    return render(request, 'helpdesk.html', {"table": table, "session": session})

@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def management_dashboard(request, restaurant_slug):
    import json
    from datetime import timedelta, datetime as dt_cls, time as time_cls, date as date_cls
    from decimal import Decimal
    from django.db.models import Sum, Count, Avg, F, ExpressionWrapper, fields, Q
    from django.core.paginator import Paginator
    from django.db.models.functions import TruncDate, TruncHour, ExtractWeekDay, ExtractHour
    from django.utils import timezone

    def _json_money(value):
        """Convert Decimals to floats so json_script output is valid JSON."""
        if isinstance(value, Decimal):
            return float(value)
        return value

    restaurant = get_dashboard_restaurant(request, restaurant_slug)

    if request.user.role == "kitchen":
        messages.error(request, "Kitchen staff don't have access to the analytics dashboard.")
        return redirect("kitchendashboard", restaurant_slug=restaurant.slug)

    today = timezone.now().date()

    def build_sales_series(buckets, start, end, is_hourly):
        """Pad a bucket list into a contiguous series with relative bar heights.

        ``buckets`` come straight from the ORM (tz-aware datetimes for hourly,
        plain ``date`` objects for daily). ``start``/``end`` must be built the
        same way so dict keys line up.
        """
        counts = {bucket['date']: float(bucket['total']) for bucket in buckets}
        max_total = max(counts.values(), default=0) or 1
        if is_hourly:
            points = [start + timedelta(hours=i) for i in range(int((end - start).total_seconds() // 3600) + 1)]
        else:
            points = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        series = []
        for point in points:
            label = point.strftime('%H:00') if is_hourly else point.strftime('%d %b')
            amount = counts.get(point, 0.0)
            height = min(100, max(10, amount / max_total * 100)) if amount > 0 else 10
            series.append({'day': label, 'amount': amount, 'height': height})
        return series

    MAX_CUSTOM_DAYS = 90
    range_param = (request.GET.get('range') or 'weekly').strip().lower()
    active_range = 'weekly'
    if range_param in ('today', 'weekly', 'monthly'):
        active_range = range_param
    elif range_param == 'custom':
        try:
            custom_from = date_cls.fromisoformat(request.GET.get('from', '').strip())
            custom_to = date_cls.fromisoformat(request.GET.get('to', '').strip()) if request.GET.get('to', '').strip() else today
            if custom_from <= custom_to and (custom_to - custom_from).days <= MAX_CUSTOM_DAYS:
                active_range = 'custom'
        except ValueError:
            pass

    if active_range == 'today':
        start_date = today
    elif active_range == 'weekly':
        start_date = today - timedelta(days=6)
    elif active_range == 'monthly':
        start_date = today - timedelta(days=29)
    else:
        start_date = custom_from
        custom_to = min(custom_to, today)

    order_items = OrderItem.objects.filter(order__table_session__restaurant=restaurant)
    orders = Order.objects.filter(table_session__restaurant=restaurant)

    if active_range == 'today':
        date_filters = {'placed_at__date': today}
    elif active_range == 'custom':
        date_filters = {'placed_at__date__gte': start_date, 'placed_at__date__lte': custom_to}
    else:
        date_filters = {'placed_at__date__gte': start_date}

    filtered_orders = orders.filter(**date_filters)
    filtered_order_items = order_items.filter(**{f'order__{k}': v for k, v in date_filters.items()})

    total_revenue = filtered_order_items.aggregate(
        total=Sum(F('quantity') * F('price_at_order'))
    )['total'] or 0

    total_orders = filtered_orders.count()

    avg_prep_time = filtered_orders.filter(
        status__in=['ready', 'served'],
        started_preparing_at__isnull=False
    ).aggregate(
        avg_time=Avg(
            ExpressionWrapper(
                F('started_preparing_at') - F('placed_at'),
                output_field=fields.DurationField()
            )
        )
    )['avg_time']

    avg_prep_minutes = 0
    if avg_prep_time:
        avg_prep_minutes = round(avg_prep_time.total_seconds() / 60)

    avg_order_value = _json_money(
        total_revenue / total_orders) if total_orders else 0.0

    # Bill analytics, scoped to table sessions opened within the same range.
    # date_filters look like {"placed_at__date__gte": ...}; reuse the suffix.
    bill_date_filter = {
        f'table_session__opened_at__{key.split("placed_at__", 1)[-1]}': value
        for key, value in date_filters.items()
    }
    bills = Bill.objects.filter(
        table_session__restaurant=restaurant, **bill_date_filter
    )
    paid_bill_stats = bills.filter(is_paid=True).aggregate(
        total_paid=Sum('amount'), paid_count=Count('id')
    )
    unpaid_bill_stats = bills.filter(is_paid=False).aggregate(
        total_outstanding=Sum('amount'), unpaid_count=Count('id')
    )

    if active_range == 'today':
        bucket = TruncHour('order__placed_at')
        series_start = timezone.make_aware(dt_cls.combine(today, time_cls.min))
        series_end = timezone.make_aware(dt_cls.combine(today, time_cls.max))
        chart_title = "Today's Sales by Hour"
    else:
        bucket = TruncDate('order__placed_at')
        series_start = start_date
        series_end = custom_to if active_range == 'custom' else today
        if active_range == 'weekly':
            chart_title = 'Weekly Sales Performance'
        elif active_range == 'monthly':
            chart_title = 'Monthly Sales Performance'
        else:
            chart_title = f'Sales Performance: {start_date:%b %d} – {custom_to:%b %d}'

    sales_buckets = filtered_order_items.annotate(
        date=bucket
    ).values('date').annotate(
        total=Sum(F('quantity') * F('price_at_order'))
    ).order_by('date')

    sales_data = build_sales_series(
        sales_buckets, series_start, series_end,
        is_hourly=(active_range == 'today')
    )

    sales_chart_labels = [entry['day'] for entry in sales_data]
    sales_chart_values = [entry['amount'] for entry in sales_data]

    # ---- Deep analytics (all respect the selected date range) ----
    # Most bought meals (top 5).
    top_meals = filtered_order_items.values(
        'menu_item__name'
    ).annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price_at_order'))
    ).order_by('-total_sold')[:5]
    top_meals = list(top_meals)
    top_meal_names = [row['menu_item__name'] or 'Unknown' for row in top_meals]
    top_meal_quantities = [row['total_sold'] for row in top_meals]
    top_meal_revenues = [_json_money(row['total_revenue']) for row in top_meals]

    # Revenue split by category (donut).
    category_mix = filtered_order_items.values(
        'menu_item__category__name'
    ).annotate(
        total_revenue=Sum(F('quantity') * F('price_at_order'))
    ).order_by('-total_revenue')[:8]
    category_names = [(row['menu_item__category__name'] or 'Uncategorised') for row in category_mix]
    category_totals = [_json_money(row['total_revenue']) for row in category_mix]

    # Orders by weekday (1=Sunday per ExtractWeekDay) and by hour.
    weekday_counts = filtered_orders.annotate(
        wd=ExtractWeekDay('placed_at')
    ).values('wd').annotate(count=Count('id'))
    weekday_map = {row['wd']: row['count'] for row in weekday_counts}
    weekday_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekday_order = [2, 3, 4, 5, 6, 7, 1]
    weekday_data = [weekday_map.get(wd, 0) for wd in weekday_order]

    hour_counts = filtered_orders.annotate(
        hr=ExtractHour('placed_at')
    ).values('hr').annotate(count=Count('id'))
    hour_map = {row['hr']: row['count'] for row in hour_counts}
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    hour_data = [hour_map.get(h, 0) for h in range(24)]

    # "Customers" = distinct table visits with orders inside the range,
    # regardless of when the session itself was opened.
    orders_in_range_filter = Q(
        orders__placed_at__date__gte=start_date,
        orders__placed_at__date__lte=custom_to if active_range == 'custom' else today,
    )
    sessions_in_range = TableSession.objects.filter(
        restaurant=restaurant
    ).annotate(order_count=Count('orders', filter=orders_in_range_filter))
    total_customers = sessions_in_range.filter(order_count__gt=0).count()
    repeat_customers = sessions_in_range.filter(order_count__gt=1).count()
    repeat_rate = round(repeat_customers / total_customers * 100) if total_customers else 0
    avg_income_per_customer = _json_money(total_revenue / total_customers) if total_customers else 0.0
    avg_ticket = _json_money(total_revenue / total_orders) if total_orders else 0.0
    avg_items_per_order = 0
    if total_orders:
        item_count = filtered_order_items.aggregate(items=Count('id'))['items'] or 0
        avg_items_per_order = round(item_count / total_orders, 1)
    top3_share = 0
    total_rev_float = _json_money(total_revenue) or 0
    if total_rev_float and len(top_meal_revenues) >= 3:
        top3_share = round(sum(top_meal_revenues[:3]) / total_rev_float * 100)
    elif total_rev_float:
        top3_share = round(sum(top_meal_revenues) / total_rev_float * 100)
    peak_weekday = weekday_labels[weekday_data.index(max(weekday_data))] if max(weekday_data, default=0) > 0 else '—'
    peak_hour_idx = hour_data.index(max(hour_data)) if max(hour_data, default=0) > 0 else None
    peak_hour = f"{peak_hour_idx:02d}:00" if peak_hour_idx is not None else '—'

    query = (request.GET.get('q') or '').strip()[:100]

    best_sellers = filtered_order_items
    if query:
        best_sellers = best_sellers.filter(menu_item__name__icontains=query)
    best_sellers = best_sellers.values(
        'menu_item__name', 'menu_item__price'
    ).annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price_at_order'))
    ).order_by('-total_sold')[:5]

    kitchen_status = orders.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    status_counts = {
        'pending': 0,
        'preparing': 0,
        'ready': 0,
        'served': 0
    }
    for status in kitchen_status:
        status_counts[status['status']] = status['count']

    total_active = status_counts['preparing'] + status_counts['ready']
    preparing_percentage = 0
    ready_percentage = 0
    if total_active > 0:
        preparing_percentage = round((status_counts['preparing'] / total_active) * 100)
        ready_percentage = round((status_counts['ready'] / total_active) * 100)

    recent_orders = orders.select_related('table_session__table').prefetch_related(
        'items__menu_item'
    ).order_by('-placed_at')
    if query:
        recent_orders = recent_orders.filter(items__menu_item__name__icontains=query).distinct()

    paginator = Paginator(recent_orders, 20)
    try:
        recent_orders_page = paginator.get_page(request.GET.get('page'))
    except Exception:
        recent_orders_page = paginator.get_page(1)

    if active_range == 'custom':
        range_from_iso = start_date.isoformat()
        range_to_iso = custom_to.isoformat()
    else:
        range_from_iso = start_date.isoformat()
        range_to_iso = today.isoformat()

    # Preserve range/search filters when paging through recent orders.
    pagination_params = request.GET.copy()
    pagination_params.pop('page', None)
    if not pagination_params:
        pagination_params['range'] = active_range
        pagination_params['from'] = range_from_iso
        pagination_params['to'] = range_to_iso
        if query:
            pagination_params['q'] = query
    pagination_qs = pagination_params.urlencode()

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'best_sellers_names': [row['menu_item__name'] or 'Unknown' for row in best_sellers],
        'best_sellers_revenues': [_json_money(row['total_revenue']) for row in best_sellers],
        'avg_prep_time': avg_prep_minutes,
        'avg_order_value': avg_order_value,
        'avg_income_per_customer': avg_income_per_customer,
        'total_customers': total_customers,
        'repeat_rate': repeat_rate,
        'avg_items_per_order': avg_items_per_order,
        'top3_share': top3_share,
        'peak_weekday': peak_weekday,
        'peak_hour': peak_hour,
        'top_meal_names': top_meal_names,
        'top_meal_quantities': top_meal_quantities,
        'top_meal_revenues': top_meal_revenues,
        'category_names': category_names,
        'category_totals': category_totals,
        'weekday_labels': weekday_labels,
        'weekday_data': weekday_data,
        'hour_labels': hour_labels,
        'hour_data': hour_data,
        'total_paid': _json_money(paid_bill_stats['total_paid']) or 0.0,
        'paid_bills': paid_bill_stats['paid_count'] or 0,
        'total_outstanding': _json_money(unpaid_bill_stats['total_outstanding']) or 0.0,
        'unpaid_bills': unpaid_bill_stats['unpaid_count'] or 0,
        'weekly_sales': sales_data,
        'sales_chart_labels': sales_chart_labels,
        'sales_chart_values': sales_chart_values,
        'chart_title': chart_title,
        'best_sellers': best_sellers,
        'kitchen_status': status_counts,
        'preparing_percentage': preparing_percentage,
        'ready_percentage': ready_percentage,
        'recent_orders': recent_orders_page,
        'tables_active': TableSession.objects.filter(status__in=["ordering", "awaiting_payment"], restaurant=restaurant).count(),
        'active_range': active_range,
        'range_from': range_from_iso,
        'range_to': range_to_iso,
        'query': query,
        'pagination_qs': pagination_qs,
        'restaurant': restaurant,
    }

    return render(request, 'dashboard.html', context)


def _resolve_menu_category(restaurant, category_id, new_category_name):
    """Return a Category for the menu form: either the chosen one or a
    newly-created category from the ``new_category`` input."""
    if new_category_name:
        name = new_category_name.strip()[:100]
        existing = Category.objects.filter(restaurant=restaurant, name__iexact=name).first()
        if existing:
            return existing
        last = Category.objects.filter(restaurant=restaurant).order_by('-display_order').first()
        return Category.objects.create(
            restaurant=restaurant,
            name=name,
            display_order=(last.display_order + 1) if last else 0,
        )
    if category_id:
        return Category.objects.filter(id=category_id, restaurant=restaurant).first()
    return None


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def menu_management(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    categories = Category.objects.filter(restaurant=restaurant).order_by('display_order', 'name')
    items = MenuItem.objects.filter(restaurant=restaurant).select_related('category').order_by('category__display_order', 'name')
    query = (request.GET.get('q') or '').strip()[:100]
    if query:
        items = items.filter(name__icontains=query)
    return render(request, 'menu_management.html', {
        'restaurant': restaurant,
        'categories': categories,
        'menu_items': items,
        'query': query,
    })


@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
def menu_item_add(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    categories = Category.objects.filter(restaurant=restaurant).order_by('display_order', 'name')

    if request.method == "POST":
        name = (request.POST.get('name') or '').strip()[:150]
        price_raw = (request.POST.get('price') or '').strip()
        if not name or not price_raw:
            messages.error(request, "Name and price are required.")
        else:
            try:
                price = Decimal(price_raw)
            except Exception:
                messages.error(request, "Price must be a number, e.g. 70.00")
            else:
                category = _resolve_menu_category(
                    restaurant, request.POST.get('category') or '', request.POST.get('new_category') or ''
                )
                stock_raw = (request.POST.get('stock_quantity') or '').strip()
                try:
                    stock = int(stock_raw) if stock_raw else None
                except ValueError:
                    stock = None
                try:
                    threshold = int(request.POST.get('low_stock_threshold') or 5)
                except ValueError:
                    threshold = 5
                item = MenuItem(
                    restaurant=restaurant,
                    category=category,
                    name=name,
                    description=(request.POST.get('description') or '').strip(),
                    price=price,
                    is_available=bool(request.POST.get('is_available')),
                    stock_quantity=stock,
                    low_stock_threshold=max(0, threshold),
                )
                image = request.FILES.get('image')
                if image:
                    item.image = image
                item.save()
                messages.success(request, f"{item.name} added to the menu.")
                return redirect('menu_management', restaurant_slug=restaurant.slug)

    return render(request, 'menu_item_form.html', {
        'restaurant': restaurant,
        'categories': categories,
        'item': None,
    })


@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
def menu_item_edit(request, restaurant_slug, item_id):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    item = get_object_or_404(MenuItem, id=item_id, restaurant=restaurant)
    categories = Category.objects.filter(restaurant=restaurant).order_by('display_order', 'name')

    if request.method == "POST":
        name = (request.POST.get('name') or '').strip()[:150]
        price_raw = (request.POST.get('price') or '').strip()
        if not name or not price_raw:
            messages.error(request, "Name and price are required.")
        else:
            try:
                price = Decimal(price_raw)
            except Exception:
                messages.error(request, "Price must be a number, e.g. 70.00")
            else:
                category = _resolve_menu_category(
                    restaurant, request.POST.get('category') or '', request.POST.get('new_category') or ''
                )
                stock_raw = (request.POST.get('stock_quantity') or '').strip()
                try:
                    stock = int(stock_raw) if stock_raw else None
                except ValueError:
                    stock = item.stock_quantity
                try:
                    threshold = int(request.POST.get('low_stock_threshold') or item.low_stock_threshold)
                except ValueError:
                    threshold = item.low_stock_threshold
                item.name = name
                item.description = (request.POST.get('description') or '').strip()
                item.price = price
                item.category = category
                item.is_available = bool(request.POST.get('is_available'))
                item.stock_quantity = stock
                item.low_stock_threshold = max(0, threshold)
                image = request.FILES.get('image')
                if image:
                    item.image = image
                item.save()
                messages.success(request, f"{item.name} updated.")
                return redirect('menu_management', restaurant_slug=restaurant.slug)

    return render(request, 'menu_item_form.html', {
        'restaurant': restaurant,
        'categories': categories,
        'item': item,
    })


@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
@require_POST
def menu_item_delete(request, restaurant_slug, item_id):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    item = get_object_or_404(MenuItem, id=item_id, restaurant=restaurant)
    name = item.name
    item.delete()
    messages.success(request, f"{name} removed from the menu.")
    return redirect('menu_management', restaurant_slug=restaurant.slug)


@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
@require_POST
def category_add(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    name = (request.POST.get('name') or '').strip()[:100]
    if not name:
        messages.error(request, "Category name is required.")
    elif Category.objects.filter(restaurant=restaurant, name__iexact=name).exists():
        messages.error(request, f"Category “{name}” already exists.")
    else:
        last = Category.objects.filter(restaurant=restaurant).order_by('-display_order').first()
        Category.objects.create(
            restaurant=restaurant, name=name,
            display_order=(last.display_order + 1) if last else 0,
        )
        messages.success(request, f"Category “{name}” created.")
    return redirect('menu_management', restaurant_slug=restaurant.slug)


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def inventory(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    items = MenuItem.objects.filter(restaurant=restaurant).select_related('category').order_by('category__display_order', 'name')
    query = (request.GET.get('q') or '').strip()[:100]
    if query:
        items = items.filter(name__icontains=query)
    low_out = [i for i in items if i.stock_status in ('low', 'out')]
    return render(request, 'inventory.html', {
        'restaurant': restaurant,
        'menu_items': items,
        'low_out_items': low_out,
        'query': query,
    })


@ratelimit(key='user_or_ip', rate='120/m', method='POST', block=True)
@restaurant_required
@require_POST
def inventory_adjust(request, restaurant_slug, item_id):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    item = get_object_or_404(MenuItem, id=item_id, restaurant=restaurant)
    try:
        delta = int(request.POST.get('delta'))
    except (TypeError, ValueError):
        delta = 0
    if delta:
        if not item.is_stock_tracked:
            messages.error(request, f"{item.name} doesn't track stock (unlimited).")
            return redirect('inventory', restaurant_slug=restaurant.slug)
        item.stock_quantity = max(0, item.stock_quantity + delta)
        if item.stock_quantity == 0:
            item.is_available = False  # auto sold-out
        elif delta > 0:
            item.is_available = True  # restocking re-lists the dish
    item.save(update_fields=["stock_quantity", "is_available"])
    if item.stock_status == 'out':
        messages.error(request, f"{item.name} is now out of stock and hidden from customers.")
    else:
        messages.success(request, f"{item.name} stock set to {item.stock_quantity if item.is_stock_tracked else '∞'}.")
    return redirect('inventory', restaurant_slug=restaurant.slug)


def _pos_get_session(table, restaurant):
    """Return the table's active ordering session, creating one lazily like
    the customer QR flow does."""
    session = TableSession.objects.filter(
        table=table, status__in=["ordering", "awaiting_payment"]
    ).first()
    if session is None:
        from django.db import IntegrityError
        try:
            session = TableSession.objects.create(
                table=table, restaurant=restaurant, status="ordering"
            )
        except IntegrityError:
            session = TableSession.objects.filter(
                table=table, status__in=["ordering", "awaiting_payment"]
            ).first()
    return session


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def pos_terminal(request, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    if request.user.role == "kitchen":
        messages.error(request, "Kitchen staff don't have access to the POS terminal.")
        return redirect("kitchendashboard", restaurant_slug=restaurant.slug)
    tables = Table.objects.filter(restaurant=restaurant).order_by('number')
    categories = Category.objects.filter(restaurant=restaurant).order_by('display_order', 'name')
    items = MenuItem.objects.filter(restaurant=restaurant, is_available=True).select_related('category')
    menu_payload = [
        {
            'id': item.id,
            'name': item.name,
            'price': float(item.price),
            'category': item.category.name if item.category_id else '—',
            'image': item.image.url if item.image else '',
            'tracked': item.is_stock_tracked,
            'stock': item.stock_quantity,
        }
        for item in items
    ]
    return render(request, 'pos.html', {
        'restaurant': restaurant,
        'tables': tables,
        'categories': categories,
        'menu_payload': menu_payload,
    })


@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
@require_POST
def pos_submit_order(request, restaurant_slug):
    import json as _json
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    table = get_object_or_404(Table, id=request.POST.get('table_id') or 0, restaurant=restaurant)
    session = _pos_get_session(table, restaurant)

    try:
        lines = _json.loads(request.POST.get('lines') or '[]')
        lines = [
            {'id': int(l['id']), 'qty': max(1, int(l['qty'])), 'notes': str(l.get('notes') or '')[:255]}
            for l in lines if l.get('id') and int(l.get('qty', 0)) > 0
        ]
    except (KeyError, TypeError, ValueError):
        messages.error(request, "Malformed order payload.")
        return redirect('pos_terminal', restaurant_slug=restaurant.slug)

    if not lines:
        messages.error(request, "Add at least one item before sending.")
        return redirect('pos_terminal', restaurant_slug=restaurant.slug)

    menu_items = {m.id: m for m in MenuItem.objects.filter(
        restaurant=restaurant, id__in=[l['id'] for l in lines])}
    unavailable = []
    missing = False
    for line in lines:
        item = menu_items.get(line['id'])
        if item is None:
            missing = True
        elif not item.is_available or (item.is_stock_tracked and item.stock_quantity < line['qty']):
            unavailable.append(item.name)
    if missing:
        messages.error(request, "One or more dishes no longer exist. Refresh and try again.")
        return redirect('pos_terminal', restaurant_slug=restaurant.slug)
    if unavailable:
        messages.error(request, "Not in stock: " + ", ".join(unavailable))
        return redirect('pos_terminal', restaurant_slug=restaurant.slug)

    paid_now = bool(request.POST.get('paid_now'))
    with transaction.atomic():
        order = Order.objects.create(table_session=session, status="pending")
        total = Decimal("0.00")
        for line in lines:
            item = menu_items[line['id']]
            OrderItem.objects.create(
                order=order,
                menu_item=item,
                quantity=line['qty'],
                price_at_order=item.price,
                notes=line['notes'],
            )
            item.decrement_stock(line['qty'])
            total += item.price * line['qty']
        if paid_now:
            bill, created = Bill.objects.get_or_create(
                table_session=session,
                defaults={"amount": total, "is_paid": True, "paid_at": timezone.now()},
            )
            if not created:
                # Additional POS payments on the same visit accumulate.
                bill.amount = (bill.amount or Decimal("0.00")) + total
                bill.is_paid = True
                bill.paid_at = timezone.now()
                bill.save(update_fields=["amount", "is_paid", "paid_at"])
            order.paid = True
            order.save(update_fields=["paid"])
            messages.success(request, f"Order #{order.id} placed and marked PAID (₵{total}).")
        else:
            messages.success(request, f"Order #{order.id} sent to the kitchen (₵{total} — pay on request).")
    return redirect('pos_terminal', restaurant_slug=restaurant.slug)


from django.db.models import F, Sum

@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
@require_POST
def close_table_session(request, table_id, restaurant_slug):
    restaurant = get_dashboard_restaurant(request, restaurant_slug)
    table = get_object_or_404(Table, id=table_id, restaurant=restaurant)
    session = TableSession.objects.filter(
        table=table, status__in=["ordering", "awaiting_payment"]
    ).first()
    if session:
        with transaction.atomic():
            total = OrderItem.objects.filter(order__table_session=session).aggregate(
                total=Sum(F("quantity") * F("price_at_order"))
            )["total"] or Decimal("0.00")
            bill, created = Bill.objects.get_or_create(
                table_session=session,
                defaults={"amount": total, "is_paid": True, "paid_at": timezone.now()},
            )
            if not created:
                bill.amount = total
                bill.is_paid = True
                bill.paid_at = timezone.now()
                bill.save(update_fields=["amount", "is_paid", "paid_at"])
            session.orders.update(paid=True)
            session.status = "closed"
            session.is_active = False
            session.closed_at = timezone.now()
            session.save(update_fields=["status", "is_active", "closed_at"])
        messages.success(request, f"Table {table.number} closed and ready for the next guests.")
    return redirect("kitchendashboard", restaurant_slug=restaurant.slug)
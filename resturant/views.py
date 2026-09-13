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
    Table,
    TableSession,
)
from .utils import get_active_session, restaurant_required


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
            if quantity > 0:
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
            session.cart_items.all().delete()
            session.status = "awaiting_payment"
            session.save(update_fields=["status"])
        return redirect("orderstatus", restaurant_slug=restaurant_slug, qr_token=qr_token)

    return redirect("table_cart", restaurant_slug=restaurant_slug, qr_token=qr_token)


@ratelimit(key='user_or_ip', rate='5/m', method='POST', block=True)
def kitchenlogin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            request.session.set_expiry(12390)
            messages.success(request, 'user is authenticated')
            return redirect('kitchendashboard')
        else:
            messages.error(request, 'user not authenticated')
            return redirect('kitchenlogin')

    return render(request, 'kitchenlogin.html')


@require_POST
def kitchenlogout(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('kitchenlogin')


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def dashboard(request):
    restaurant = request.user.restaurant
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
    return render(request, 'kitchendashboard.html', {
        "orders": orders,
        "live_ticket_count": live_ticket_count,
        "tables_active": tables_active,
        "tables_with_bill_request": tables_with_bill_request,
        "restaurant": restaurant,
    })

VALID_ORDER_STATUSES = {"pending", "preparing", "ready", "served"}

@ratelimit(key='user_or_ip', rate='60/m', method='POST', block=False)
@restaurant_required
@require_POST
def advance_order_status(request, order_id):
    if getattr(request, 'limited', False):
        messages.error(request, "You're updating tickets too quickly — please wait a moment and try again.")
        return redirect("kitchendashboard")

    restaurant = request.user.restaurant
    order = get_object_or_404(Order, id=order_id, table_session__restaurant=restaurant)
    new_status = request.POST.get("status")

    if new_status not in VALID_ORDER_STATUSES:
        messages.error(request, "Invalid status update.")
        return redirect("kitchendashboard")

    order.status = new_status
    if new_status == "preparing":
        order.started_preparing_at = timezone.now()
    order.save()

    messages.success(request, f"Order #{order.id} marked as {order.get_status_display()}.")
    return redirect("kitchendashboard")

@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def kitchendisplay(request):
    restaurant = request.user.restaurant
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
def mark_table_orders_ready(request, table_id):
    restaurant = request.user.restaurant
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
    return redirect('kitchendashboard')


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
@restaurant_required
def kitchendisplaywidget(request):
    restaurant = request.user.restaurant
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
def management_dashboard(request):
    from datetime import timedelta, datetime as dt_cls, time as time_cls, date as date_cls
    from django.db.models import Sum, Count, Avg, F, ExpressionWrapper, fields
    from django.db.models.functions import TruncDate, TruncHour
    from django.utils import timezone

    restaurant = request.user.restaurant

    if request.user.role == "kitchen":
        messages.error(request, "Kitchen staff don't have access to the analytics dashboard.")
        return redirect("kitchendashboard")

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

    avg_prep_time = orders.filter(
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
    )
    if query:
        recent_orders = recent_orders.filter(items__menu_item__name__icontains=query).distinct()
    recent_orders = recent_orders.order_by('-placed_at')[:10]

    if active_range == 'custom':
        range_from_iso = start_date.isoformat()
        range_to_iso = custom_to.isoformat()
    else:
        range_from_iso = start_date.isoformat()
        range_to_iso = today.isoformat()

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_prep_time': avg_prep_minutes,
        'weekly_sales': sales_data,
        'chart_title': chart_title,
        'best_sellers': best_sellers,
        'kitchen_status': status_counts,
        'preparing_percentage': preparing_percentage,
        'ready_percentage': ready_percentage,
        'recent_orders': recent_orders,
        'tables_active': TableSession.objects.filter(status__in=["ordering", "awaiting_payment"], restaurant=restaurant).count(),
        'active_range': active_range,
        'range_from': range_from_iso,
        'range_to': range_to_iso,
        'query': query,
        'restaurant': restaurant,
    }

    return render(request, 'dashboard.html', context)


from django.db.models import F, Sum

@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@restaurant_required
@require_POST
def close_table_session(request, table_id):
    restaurant = request.user.restaurant
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
    return redirect("kitchendashboard")
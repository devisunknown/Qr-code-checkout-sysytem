from django.shortcuts import render,redirect,get_object_or_404
from .utils import get_active_session,TableSession,Table
from .models import MenuItem, Table, TableSession, CartItem, Category, Order, OrderItem
from django.contrib.auth import authenticate,login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit


@ratelimit(key='user', rate='5/m', method='POST', block=True)
def index(request, qr_token):
    table, session = get_active_session(qr_token)
    query = request.GET.get("q", "").strip()

    menu_items = MenuItem.objects.filter(is_available=True).select_related("category")
    if query:
        menu_items = menu_items.filter(name__icontains=query)

    categories = Category.objects.all()
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

@ratelimit(key='user', rate='5/m', method='POST', block=True)
def cart(request, qr_token):
    table, session = get_active_session(qr_token)

    if request.method == "POST":
        menu_item_id = request.POST.get("menu_item_id")
        if menu_item_id:
            menu_item = get_object_or_404(MenuItem, id=menu_item_id)
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
        return redirect("table_cart", qr_token=qr_token)

    items = session.cart_items.select_related("menu_item")
    # Attach line_total to each cart item for template use
    for item in items:
        item.line_total = item.menu_item.price * item.quantity
    total = sum(item.menu_item.price * item.quantity for item in items)
    return render(request, 'cart.html', {"table": table, "session": session, "items": items, "total": total})


@ratelimit(key='user', rate='5/m', method='POST', block=True)
def checkout(request, qr_token):
    table, session = get_active_session(qr_token)
    items = session.cart_items.select_related("menu_item")
    total = sum(item.menu_item.price * item.quantity for item in items)

    if not items.exists():
        return redirect('table_cart', qr_token=qr_token)

    return render(request, 'checkout.html', {
        "table": table,
        "session": session,
        "items": items,
        "total": total,
    })


@ratelimit(key='user', rate='60/m', method='GET', block=True)
def orderstatus(request, qr_token):
    table, session = get_active_session(qr_token)
    orders = session.orders.prefetch_related("items__menu_item")
    return render(request, 'orderstatus.html', {"table": table, "session": session, "orders": orders})


@ratelimit(key='user', rate='60/m', method='GET', block=True)
def successful_order(request, qr_token):
    table, session = get_active_session(qr_token)
    return render(request, 'successful_order.html', {"table": table, "session": session})

@ratelimit(key='user', rate='60/m', method='GET', block=True)
def request_bill(request, qr_token):
    table, session = get_active_session(qr_token)

    orders = session.orders.exclude(status='served')

    if orders.exists():
        orders.update(bill_requested=True)

        items = list(OrderItem.objects.filter(order__in=orders).select_related("menu_item"))
        for item in items:
            item.line_total = item.price_at_order * item.quantity
        total = sum(item.line_total for item in items)

        order = orders.order_by('-placed_at').first()
        messages.info(request, "Bill requested successfully.")
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


@ratelimit(key='user', rate='60/m', method='POST', block=True)
def cart_update(request, qr_token, item_id):
    table, session = get_active_session(qr_token)
    cart_item = get_object_or_404(CartItem, id=item_id, table_session=session)

    if request.method == "POST":
        quantity = request.POST.get("quantity")
        try:
            new_quantity = int(quantity)
        except (TypeError, ValueError):
            new_quantity = cart_item.quantity

        if new_quantity <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = new_quantity
            cart_item.save()

    return redirect("table_cart", qr_token=qr_token)


@ratelimit(key='user', rate='60/m', method='POST', block=True)
def cart_remove(request, qr_token, item_id):
    table, session = get_active_session(qr_token)
    cart_item = get_object_or_404(CartItem, id=item_id, table_session=session)
    cart_item.delete()
    return redirect("table_cart", qr_token=qr_token)


@ratelimit(key='user', rate='60/m', method='POST', block=True)
def cart_send(request, qr_token):
    table, session = get_active_session(qr_token)
    items = session.cart_items.select_related("menu_item")

    if request.method == "POST" and items.exists():
        order = Order.objects.create(table_session=session, status="pending")
        for item in items:
            OrderItem.objects.create(
                order=order,
                menu_item=item.menu_item,
                quantity=item.quantity,
                price_at_order=item.menu_item.price,
            )
        items.delete()
        session.status = "awaiting_payment"
        session.save(update_fields=["status"])
        return redirect("orderstatus", qr_token=qr_token)

    return redirect("table_cart", qr_token=qr_token)


@ratelimit(key='user', rate='5/m', method='POST', block=True)
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


@ratelimit(key='user', rate='60/m', method='GET', block=True)
@login_required
def dashboard(request):
    orders = (Order.objects
                  .filter(table_session__status__in=["ordering", "awaiting_payment"])
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
    })

VALID_ORDER_STATUSES = {"pending", "preparing", "ready", "served"}

@ratelimit(key='user', rate='60/m', method='POST', block=False)
@login_required
@require_POST
def advance_order_status(request, order_id):
    if getattr(request, 'limited', False):
        messages.error(request, "You're updating tickets too quickly — please wait a moment and try again.")
        return redirect("kitchendashboard")

    order = get_object_or_404(Order, id=order_id)
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

@ratelimit(key='user', rate='60/m', method='GET', block=True)
@login_required
def kitchendisplay(request):
    orders = (Order.objects.exclude(status="served")
              .select_related("table_session__table")
              .prefetch_related("items__menu_item")
              .order_by("placed_at"))
    return render(request, 'kitchendisplay.html', {
        "orders": orders,
        "live_ticket_count": orders.count(),
        "tables_active": TableSession.objects.filter(status__in=["ordering", "awaiting_payment"]).count(),
    })


@ratelimit(key='user', rate='60/m', method='POST', block=True)
@login_required
def mark_table_orders_ready(request, table_id):
    if request.method == 'POST':
        try:
            updated = Order.objects.filter(
                table_session__table_id=table_id, status='preparing'
            ).update(status='ready')

            ready_orders = Order.objects.filter(table_session__table_id=table_id, status='ready')
            if ready_orders.exists():
                messages.success(
                    request,
                    f'{ready_orders.count()} order(s) for table marked as ready. Customers will be notified.'
                )
                ready_orders.delete()
            else:
                messages.info(request, 'No preparing orders found for this table.')
        except Exception as e:
            messages.error(request, f'An error occurred while marking orders as ready: {str(e)}')
    return redirect('kitchendashboard')


@ratelimit(key='user', rate='60/m', method='GET', block=True)
@login_required
def kitchendisplaywidget(request):
    orders = (Order.objects.exclude(status="served")
              .select_related("table_session__table")
              .prefetch_related("items__menu_item")
              .order_by("placed_at"))
    return render(request, 'kitchendisplaywidget.html', {
        "orders": orders,
        "live_ticket_count": orders.count(),
        "tables_active": TableSession.objects.filter(status__in=["ordering", "awaiting_payment"]).count(),
        
    })
@ratelimit(key='user', rate='5/m', method='GET', block=True)
def helpdesk(request, qr_token):
    table, session = get_active_session(qr_token)
    return render(request, 'helpdesk.html', {"table": table, "session": session})

@ratelimit(key='user', rate='60/m', method='GET', block=True)
@login_required
def management_dashboard(request):
    from django.db.models import Sum, Count, Avg, F, ExpressionWrapper, fields, DateTimeField
    from django.db.models.functions import TruncDate
    from django.utils import timezone
    from datetime import timedelta


    today = timezone.now().date()
    week_ago = today - timedelta(days=7)

    total_revenue = OrderItem.objects.aggregate(
        total=Sum(F('quantity') * F('price_at_order'))
    )['total'] or 0

    total_orders = Order.objects.count()

    avg_prep_time = Order.objects.filter(
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

    weekly_sales = OrderItem.objects.filter(
        order__placed_at__date__gte=week_ago
    ).annotate(
        date=TruncDate('order__placed_at')
    ).values('date').annotate(
        total=Sum(F('quantity') * F('price_at_order'))
    ).order_by('date')

    weekly_data = []
    for day in range(7):
        day_date = today - timedelta(days=6-day)
        day_data = next((item for item in weekly_sales if item['date'] == day_date), None)
        if day_data:
            weekly_data.append({
                'day': day_date.strftime('%a').upper(),
                'amount': float(day_data['total']),
                'height': min(100, max(10, float(day_data['total']) / max(1, float(max([item['total'] for item in weekly_sales], default=1))) * 100)) if max([item['total'] for item in weekly_sales], default=1) > 0 else 10
            })
        else:
            weekly_data.append({
                'day': day_date.strftime('%a').upper(),
                'amount': 0,
                'height': 10
            })

    best_sellers = OrderItem.objects.values(
        'menu_item__name', 'menu_item__price'
    ).annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price_at_order'))
    ).order_by('-total_sold')[:5]

    kitchen_status = Order.objects.values('status').annotate(
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

    recent_orders = Order.objects.select_related('table_session__table').prefetch_related(
        'items__menu_item'
    ).order_by('-placed_at')[:10]

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_prep_time': avg_prep_minutes,
        'weekly_sales': weekly_data,
        'best_sellers': best_sellers,
        'kitchen_status': status_counts,
        'preparing_percentage': preparing_percentage,
        'ready_percentage': ready_percentage,
        'recent_orders': recent_orders,
        'tables_active': TableSession.objects.filter(status__in=["ordering", "awaiting_payment"]).count(),
    }

    return render(request, 'dashboard.html', context)


from django.utils import timezone

@ratelimit(key='user', rate='30/m', method='POST', block=True)
@login_required
@require_POST
def close_table_session(request, table_id):
    table = get_object_or_404(Table, id=table_id)
    session = TableSession.objects.filter(
        table=table, status__in=["ordering", "awaiting_payment"]
    ).first()
    if session:
        session.orders.update(paid=True)
        session.status = "closed"
        session.is_active = False
        session.closed_at = timezone.now()
        session.save()
        messages.success(request, f"Table {table.number} closed and ready for the next guests.")
    return redirect("kitchendashboard")
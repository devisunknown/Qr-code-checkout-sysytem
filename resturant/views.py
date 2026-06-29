from django.shortcuts import render,redirect,get_object_or_404
from .utils import get_active_session,TableSession,Table
from .models import MenuItem, Table, TableSession, CartItem, Category, Order, OrderItem
from django.contrib.auth import authenticate
from django.contrib.auth.models import User 
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST

def index(request, qr_token):
    table, session = get_active_session(qr_token)
    menu_items = MenuItem.objects.filter(is_available=True).select_related("category")
    return render(request, 'index.html', {"table": table, "session": session, "menu_items": menu_items})


def cart(request, qr_token):
    table, session = get_active_session(qr_token)
    items = session.cart_items.select_related("menu_item")
    total = sum(item.menu_item.price * item.quantity for item in items)
    return render(request, 'cart.html', {"table": table, "session": session, "items": items, "total": total})


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

def orderstatus(request, qr_token):
    table, session = get_active_session(qr_token)
    orders = session.orders.prefetch_related("items__menu_item")
    return render(request, 'orderstatus.html', {"table": table, "session": session, "orders": orders})


def successful_order(request, qr_token):
    table, session = get_active_session(qr_token)
    return render(request, 'successful_order.html', {"table": table, "session": session})


def kitchenlogin(request):
    if request.method =='POST':
        username=request.POST.get('username')
        password=request.POST.get('password')
        User=authenticate(username=username,password=password)
        if User is not None:
            request.session.set_expiry(12390)
            messages.success(request,'user is authenticated')
            return redirect('kitchendashboard')
        else:
            messages.error(request,'user not authenticated')
            return redirect('kitchenlogin')
        
    return render(request,'kitchenlogin.html')


@login_required
def kitchendashboard(request):
    orders = (Order.objects.exclude(status="served")
              .select_related("table_session__table")
              .prefetch_related("items__menu_item")
              .order_by("placed_at"))
    return render(request, 'kitchendashboard.html', {
        "orders": orders,
        "live_ticket_count": orders.count(),
        "tables_active": TableSession.objects.filter(status__in=["ordering", "awaiting_payment"]).count(),
    })

@login_required
@require_POST
def advance_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get("status")
    if new_status in dict(Order.Status.choices if hasattr(Order, "Status") else []):
        order.status = new_status
        order.save()
    return redirect('kitchendashboard')
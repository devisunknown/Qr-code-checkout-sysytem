
from functools import wraps

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import IntegrityError

from .models import Restaurant, Table, TableSession


DASHBOARD_RESTAURANT_SESSION_KEY = "dashboard_restaurant_id"


def restaurant_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("kitchenlogin")
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if request.user.restaurant is None:
            messages.error(
                request,
                "Your account isn't linked to a restaurant. Please contact the system administrator.",
            )
            return redirect("kitchenlogin")
        return view_func(request, *args, **kwargs)

    return _wrapped


def get_dashboard_restaurant(request):
    """Resolve which restaurant's data a staff dashboard request targets.

    Staff/owner/kitchen accounts are always bound to their own restaurant.
    Superusers may view any active restaurant: the choice comes from
    ``?restaurant=<id>`` (persisted in the session) and falls back to the
    first active restaurant. Returns ``None`` when no active restaurant exists.
    """
    user = request.user

    if not user.is_superuser:
        return user.restaurant

    requested = request.GET.get("restaurant")
    if requested and str(requested).isdigit():
        restaurant = Restaurant.objects.filter(
            id=int(requested), is_active=True
        ).first()
        if restaurant is not None:
            request.session[DASHBOARD_RESTAURANT_SESSION_KEY] = restaurant.id
            return restaurant

    stored = request.session.get(DASHBOARD_RESTAURANT_SESSION_KEY)
    if stored:
        restaurant = Restaurant.objects.filter(id=stored, is_active=True).first()
        if restaurant is not None:
            return restaurant

    return Restaurant.objects.filter(is_active=True).first()


def get_active_session(restaurant_slug, qr_token):
    table = get_object_or_404(Table, qr_token=qr_token, restaurant__slug=restaurant_slug)
    session = TableSession.objects.filter(
        table=table, status__in=["ordering", "awaiting_payment"]
    ).first()
    if session is None:
        try:
            session = TableSession.objects.create(
                table=table, restaurant=table.restaurant, status="ordering"
            )
        except IntegrityError:
            session = TableSession.objects.filter(
                table=table, status__in=["ordering", "awaiting_payment"]
            ).first()
    return table, session

from functools import wraps

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import IntegrityError

from .models import Restaurant, Table, TableSession


def restaurant_required(view_func):
    """Ensure the request targets a restaurant the user is allowed to manage.

    Canonical staff routes carry ``restaurant_slug`` in the URL. Staff/owner/
    kitchen accounts may only open their own restaurant; superusers may open any.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        slug = kwargs.get("restaurant_slug")
        if not request.user.is_authenticated:
            if slug:
                return redirect("kitchenlogin", restaurant_slug=slug)
            return redirect("legacy_kitchen_login")

        user = request.user
        if not user.is_superuser:
            if user.restaurant is None:
                messages.error(
                    request,
                    "Your account isn't linked to a restaurant. Please contact the system administrator.",
                )
                if slug:
                    return redirect("kitchenlogin", restaurant_slug=slug)
                return redirect("legacy_kitchen_login")
            if slug and slug != user.restaurant.slug:
                messages.error(request, "You don't have access to that restaurant.")
                return redirect(
                    "kitchendashboard", restaurant_slug=user.restaurant.slug
                )
        return view_func(request, *args, **kwargs)

    return _wrapped


def get_dashboard_restaurant(request, restaurant_slug=None):
    """Resolve which restaurant's data a staff dashboard request targets.

    On the canonical slug-scoped routes ``restaurant_slug`` is authoritative and
    an unknown or inactive slug raises 404. When omitted, staff fall back to
    their own restaurant and superusers to the first active restaurant.
    """
    if restaurant_slug:
        return get_object_or_404(Restaurant, slug=restaurant_slug, is_active=True)

    user = request.user
    if not user.is_superuser:
        return user.restaurant
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
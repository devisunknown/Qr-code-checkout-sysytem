
from functools import wraps

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import IntegrityError

from .models import Table, TableSession


def restaurant_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("kitchenlogin")
        if request.user.restaurant is None:
            messages.error(
                request,
                "Your account isn't linked to a restaurant. Please contact the system administrator.",
            )
            return redirect("kitchenlogin")
        return view_func(request, *args, **kwargs)

    return _wrapped


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
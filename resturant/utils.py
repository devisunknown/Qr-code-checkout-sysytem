
from django.shortcuts import get_object_or_404
from django.db import IntegrityError

from .models import Table, TableSession


def get_active_session(qr_token):
    table = get_object_or_404(Table, qr_token=qr_token)
    session = TableSession.objects.filter(
        table=table, status__in=["ordering", "awaiting_payment"]
    ).first()
    if session is None:
        try:
            session = TableSession.objects.create(table=table, status="ordering")
        except IntegrityError:
            session = TableSession.objects.get(table=table, status__in=["ordering", "awaiting_payment"])
    return table, session
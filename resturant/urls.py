from django.urls import path
from . import views

urlpatterns = [
    path("t/<uuid:qr_token>/", views.index, name="table_menu"),
    path("t/<uuid:qr_token>/cart/", views.cart, name="table_cart"),
    path("t/<uuid:qr_token>/orderstatus/", views.orderstatus, name="orderstatus"),
    path("t/<uuid:qr_token>/checkout/", views.checkout, name="checkout"),
    path("t/<uuid:qr_token>/success/",views.successful_order , name="successful_order"),
    path("kitchen/login/", views.kitchenlogin, name="kitchenlogin"),
    path("kitchen/dashboard/", views.kitchendashboard, name="kitchendashboard"),
]
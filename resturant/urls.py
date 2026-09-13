from django.urls import path
from . import views

urlpatterns = [
    path("<slug:restaurant_slug>/<uuid:qr_token>/", views.index, name="table_menu"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/", views.cart, name="table_cart"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/update/<int:item_id>/", views.cart_update, name="cart_update"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/remove/<int:item_id>/", views.cart_remove, name="cart_remove"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/send/", views.cart_send, name="cart_send"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/orderstatus/", views.orderstatus, name="orderstatus"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/orderstatus/refresh/", views.orderstatus_refresh, name="orderstatus_refresh"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/request-bill/", views.request_bill, name="request_bill"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/help/", views.helpdesk, name='helpdesk'),
    path("kitchen/login/", views.kitchenlogin, name="kitchenlogin"),
    path("kitchen/logout/", views.kitchenlogout, name="kitchenlogout"),
    path("kitchen/dashboard/", views.dashboard, name="kitchendashboard"),
    path("kitchen/display/", views.kitchendisplay, name="kitchendisplay"),
    path("kitchen/order/<int:order_id>/status/", views.advance_order_status, name="advance_order_status"),
    path("kitchen/table/<int:table_id>/mark-ready/", views.mark_table_orders_ready, name="mark_table_orders_ready"),
    path("kitchen/displaywidget/", views.kitchendisplaywidget, name="kitchendisplaywidget"),
    path('<slug:restaurant_slug>/<uuid:qr_token>/help/', views.helpdesk, name='helpdesk'),
    path("dashboard/", views.management_dashboard, name="dashboard"),
    path("table/<int:table_id>/close/", views.close_table_session, name="close_table_session"),
]
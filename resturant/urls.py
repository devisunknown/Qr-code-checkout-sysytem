from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url="/static/favicon.ico", permanent=True)),

    # Legacy non-slug staff routes. These MUST come before the slug-scoped
    # routes below: "/kitchen/dashboard/" would otherwise be captured by
    # "<slug>/dashboard/" with restaurant_slug="kitchen".
    path("kitchen/login/", views.legacy_kitchen_login, name="legacy_kitchen_login"),
    path("kitchen/logout/", views.kitchenlogout, name="kitchenlogout_legacy"),
    path("kitchen/dashboard/", views.legacy_kitchen_dashboard, name="legacy_kitchen_dashboard"),
    path("kitchen/display/", views.legacy_kitchen_display, name="legacy_kitchen_display"),
    path("kitchen/displaywidget/", views.legacy_kitchen_displaywidget, name="legacy_kitchen_displaywidget"),
    path("kitchen/order/<int:order_id>/status/", views.legacy_advance_order_status, name="legacy_advance_order_status"),
    path("kitchen/table/<int:table_id>/mark-ready/", views.legacy_mark_table_orders_ready, name="legacy_mark_table_orders_ready"),
    path("dashboard/", views.legacy_management_dashboard, name="legacy_dashboard"),
    path("table/<int:table_id>/close/", views.legacy_close_table_session, name="legacy_close_table_session"),

    # Customer-facing (table QR) routes
    path("<slug:restaurant_slug>/<uuid:qr_token>/", views.index, name="table_menu"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/", views.cart, name="table_cart"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/update/<int:item_id>/", views.cart_update, name="cart_update"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/remove/<int:item_id>/", views.cart_remove, name="cart_remove"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/cart/send/", views.cart_send, name="cart_send"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/orderstatus/", views.orderstatus, name="orderstatus"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/orderstatus/refresh/", views.orderstatus_refresh, name="orderstatus_refresh"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/request-bill/", views.request_bill, name="request_bill"),
    path("<slug:restaurant_slug>/<uuid:qr_token>/help/", views.helpdesk, name="helpdesk"),

    # Staff / admin routes, scoped to a restaurant slug
    path("<slug:restaurant_slug>/kitchen/login/", views.kitchenlogin, name="kitchenlogin"),
    path("<slug:restaurant_slug>/kitchen/logout/", views.kitchenlogout, name="kitchenlogout"),
    path("<slug:restaurant_slug>/kitchen/dashboard/", views.dashboard, name="kitchendashboard"),
    path("<slug:restaurant_slug>/kitchen/display/", views.kitchendisplay, name="kitchendisplay"),
    path("<slug:restaurant_slug>/kitchen/displaywidget/", views.kitchendisplaywidget, name="kitchendisplaywidget"),
    path("<slug:restaurant_slug>/kitchen/order/<int:order_id>/status/", views.advance_order_status, name="advance_order_status"),
    path("<slug:restaurant_slug>/kitchen/table/<int:table_id>/mark-ready/", views.mark_table_orders_ready, name="mark_table_orders_ready"),
    path("<slug:restaurant_slug>/dashboard/", views.management_dashboard, name="dashboard"),
    path("<slug:restaurant_slug>/table/<int:table_id>/close/", views.close_table_session, name="close_table_session"),
]

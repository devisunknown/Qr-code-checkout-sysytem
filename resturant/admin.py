from django.contrib import admin
from .models import Table, MenuItem, Category, TableSession, Order, OrderItem, Bill, CartItem


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('number', 'qr_token')


@admin.register(TableSession)
class TableSessionAdmin(admin.ModelAdmin):
    list_display = ('table', 'is_active', 'status', 'opened_at', 'closed_at')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_order')


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_available', 'created_at')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('table_session', 'menu_item', 'quantity', 'added_by_device')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('table_session', 'status', 'paid', 'bill_requested', 'placed_at')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'menu_item', 'quantity', 'price_at_order')


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('table_session', 'amount', 'is_paid', 'paid_at')
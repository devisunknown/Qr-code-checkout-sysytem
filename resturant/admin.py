from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Restaurant, User, Table, MenuItem, Category, TableSession, Order, OrderItem, Bill, CartItem


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'phone', 'is_active', 'created_at')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'restaurant', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'restaurant')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Restaurant', {'fields': ('restaurant', 'role')}),
    )


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('number', 'restaurant', 'qr_token')
    list_filter = ('restaurant',)


@admin.register(TableSession)
class TableSessionAdmin(admin.ModelAdmin):
    list_display = ('table', 'restaurant', 'is_active', 'status', 'opened_at', 'closed_at')
    list_filter = ('restaurant', 'status')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'display_order')
    list_filter = ('restaurant',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'category', 'price', 'is_available', 'created_at')
    list_filter = ('restaurant', 'category')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('table_session', 'menu_item', 'quantity', 'added_by_device')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('table_session', 'status', 'paid', 'bill_requested', 'placed_at')
    list_filter = ('status', 'paid')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'menu_item', 'quantity', 'price_at_order')


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('table_session', 'amount', 'is_paid', 'paid_at')

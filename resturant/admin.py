from django.contrib import admin
from .models import Table, MenuItem, Category, TableSession, Order, OrderItem, Bill


class SortedAdmin(admin.ModelAdmin):
    list_filter = ('opened_at', 'closed_at')


admin.site.register(Table)
admin.site.register(MenuItem)
admin.site.register(Category)
admin.site.register(TableSession, SortedAdmin)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Bill)
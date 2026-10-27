from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
import uuid
from cloudinary.models import CloudinaryField


class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    logo = CloudinaryField("image", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("staff", "Staff"),
        ("kitchen", "Kitchen"),
    ]
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="staff")

    def clean(self):
        super().clean()
        # Every real account must belong to exactly one restaurant so the
        # dashboard can scope its data. The platform superuser is exempt.
        if self.is_superuser:
            return
        if self.restaurant_id is None:
            raise ValidationError(
                {"restaurant": "Staff accounts must be linked to a restaurant."}
            )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Table(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="tables")
    number = models.PositiveIntegerField()
    qr_token = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        unique_together = ("restaurant", "number")

    def __str__(self):
        return f"Table {self.number}"


class TableSession(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name="sessions")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="sessions")
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=[("ordering", "Ordering"), ("awaiting_payment", "Awaiting payment"), ("closed", "Closed")],
        default="ordering",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["table"],
                name="one_active_session_per_table",
                condition=models.Q(status__in=["ordering", "awaiting_payment"]),
            )
        ]


class Category(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="menu_items")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = CloudinaryField("image", blank=True, null=True)
    is_available = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Units left for this dish. Leave blank to track unlimited stock.",
    )
    low_stock_threshold = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__display_order", "name"]

    @property
    def is_stock_tracked(self):
        return self.stock_quantity is not None

    @property
    def stock_status(self):
        """'out' | 'low' | 'ok' — used for badges on staff pages."""
        if not self.is_stock_tracked or not self.is_available:
            return "ok"
        if self.stock_quantity == 0:
            return "out"
        if self.stock_quantity <= self.low_stock_threshold:
            return "low"
        return "ok"

    def decrement_stock(self, quantity):
        """Take ``quantity`` units off after an order is placed.

        Returns a short status string for flash messages: 'ok', 'low' or
        'soldout'. Sold-out items are automatically flagged unavailable so
        they disappear from the customer menu.
        """
        if not self.is_stock_tracked:
            return "ok"
        self.stock_quantity = max(0, self.stock_quantity - quantity)
        if self.stock_quantity == 0:
            self.is_available = False
        elif self.stock_quantity <= self.low_stock_threshold:
            self.save(update_fields=["stock_quantity"])
            return "low"
        self.save(update_fields=["stock_quantity", "is_available"])
        return "low" if self.stock_quantity <= self.low_stock_threshold else "ok"

    def __str__(self):
        return self.name


class CartItem(models.Model):
    table_session = models.ForeignKey(TableSession, on_delete=models.CASCADE, related_name="cart_items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=255, blank=True)
    added_by_device = models.CharField(max_length=64, blank=True)


class Order(models.Model):
    table_session = models.ForeignKey(TableSession, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(
        max_length=10,
        choices=[
            ("pending", "Pending"),
            ("preparing", "Preparing"),
            ("ready", "Ready"),
            ("served", "Served"),
        ],
        default="pending",
    )
    paid = models.BooleanField(default=False)
    bill_requested = models.BooleanField(default=False)
    started_preparing_at = models.DateTimeField(null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_order = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)


class Bill(models.Model):
    table_session = models.OneToOneField(TableSession, on_delete=models.CASCADE, related_name="bill")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paystack_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)

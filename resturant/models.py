from django.db import models
import uuid
from cloudinary.models import CloudinaryField



class Table(models.Model):
    number = models.PositiveIntegerField(unique=True)
    qr_token = models.UUIDField(default=uuid.uuid4, editable=False)
    
    
    
    
    def __str__(self):
       return f"Table {self.number}"

class TableSession(models.Model):
    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=[("ordering","Ordering"), ("awaiting_payment","Awaiting payment"), ("closed","Closed")],
        default="ordering" 
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)




class Category(models.Model):
    name = models.CharField(max_length=100)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name





class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="items")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)  
    image = CloudinaryField("image", blank=True, null=True)
    is_available = models.BooleanField(default=True)  #
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category__display_order", "name"]

    def __str__(self):
        return self.name
    

class CartItem(models.Model):
    table_session = models.ForeignKey(TableSession, on_delete=models.CASCADE, related_name="cart_items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=255, blank=True)
    added_by_device = models.CharField(max_length=64, blank=True)  # optional, for "who added this"

class Order(models.Model):
    table_session = models.ForeignKey(TableSession, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(max_length=10, choices=[("pending","Pending"),("preparing","Preparing"),("ready","Ready"),("served","Served")], default="pending")
    paid = models.BooleanField(default=False)
    bill_requested = models.BooleanField(default=False)
    started_preparing_at = models.DateTimeField(null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem , on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_order = models.DecimalField(max_digits=10, decimal_places=2)






class Bill(models.Model):

    table_session = models.OneToOneField(TableSession, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paystack_reference = models.UUIDField(default=uuid.uuid4, editable=False)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)



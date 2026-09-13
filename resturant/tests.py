from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from resturant.models import (
    Restaurant,
    Table,
    TableSession,
    Category,
    MenuItem,
    CartItem,
    Order,
    OrderItem,
    Bill,
)

User = get_user_model()


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(
            name="Test Kitchen",
            slug="test-kitchen",
        )
        cls.other_restaurant = Restaurant.objects.create(
            name="Other Place",
            slug="other-place",
        )
        cls.table = Table.objects.create(
            restaurant=cls.restaurant,
            number=1,
        )
        cls.other_table = Table.objects.create(
            restaurant=cls.other_restaurant,
            number=1,
        )
        cls.starters = Category.objects.create(
            restaurant=cls.restaurant,
            name="Starters",
            display_order=0,
        )
        cls.mains = Category.objects.create(
            restaurant=cls.restaurant,
            name="Mains",
            display_order=1,
        )
        cls.fries = MenuItem.objects.create(
            restaurant=cls.restaurant,
            category=cls.starters,
            name="Fries",
            price=5.00,
            is_available=True,
        )
        cls.burger = MenuItem.objects.create(
            restaurant=cls.restaurant,
            category=cls.mains,
            name="Burger",
            price=12.00,
            is_available=True,
        )
        cls.unavailable = MenuItem.objects.create(
            restaurant=cls.restaurant,
            category=cls.mains,
            name="Hidden",
            price=20.00,
            is_available=False,
        )
        cls.other_item = MenuItem.objects.create(
            restaurant=cls.other_restaurant,
            name="Other Dish",
            price=99.00,
        )
        cls.kitchen_user = User.objects.create_user(
            username="kitchen",
            password="testpass123",
            restaurant=cls.restaurant,
            role="kitchen",
        )
        cls.owner_user = User.objects.create_user(
            username="owner",
            password="testpass123",
            restaurant=cls.restaurant,
            role="owner",
        )

    def setUp(self):
        self.client = Client()
        self.prefix = f"/{self.restaurant.slug}/{self.table.qr_token}"
        self.other_prefix = f"/{self.other_restaurant.slug}/{self.other_table.qr_token}"


class TestMenuScoping(BaseTestCase):
    def test_index_shows_only_this_restaurants_menu(self):
        resp = self.client.get(f"{self.prefix}/")
        self.assertEqual(resp.status_code, 200)
        items = resp.context["menu_items"]
        self.assertTrue(all(i.restaurant == self.restaurant for i in items))
        self.assertFalse(items.filter(pk=self.other_item.pk).exists())
        self.assertNotContains(resp, self.other_item.name)

    def test_index_hides_unavailable_items(self):
        resp = self.client.get(f"{self.prefix}/")
        items = resp.context["menu_items"]
        self.assertFalse(items.filter(pk=self.unavailable.pk).exists())

    def test_index_scoped_categories(self):
        resp = self.client.get(f"{self.prefix}/")
        self.assertTrue(all(c.restaurant == self.restaurant for c in resp.context["categories"]))
        self.assertContains(resp, self.starters.name)

    def test_cart_rejects_other_restaurants_menu_item(self):
        resp = self.client.post(
            f"{self.prefix}/cart/",
            {"menu_item_id": self.other_item.id, "quantity": 1},
        )
        self.assertEqual(resp.status_code, 404)

    def test_cart_update_rejects_other_restaurants_item(self):
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        # item id exists but is not in this table's session — different restaurant
        resp = self.client.post(
            f"{self.other_prefix}/cart/update/{ci.id}/",
            {"quantity": 2},
        )
        self.assertIn(resp.status_code, (404, 302))


class TestCartLifecycle(BaseTestCase):
    def test_add_to_cart_increments_quantity(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        self.client.post(
            f"{self.prefix}/cart/",
            {"menu_item_id": self.fries.id, "quantity": 1},
        )
        self.client.post(
            f"{self.prefix}/cart/",
            {"menu_item_id": self.fries.id, "quantity": 2},
        )
        ci = CartItem.objects.get(table_session=session, menu_item=self.fries)
        self.assertEqual(ci.quantity, 3)

    def test_cart_update_quantity(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        self.client.post(
            f"{self.prefix}/cart/update/{ci.id}/",
            {"quantity": 5},
        )
        ci.refresh_from_db()
        self.assertEqual(ci.quantity, 5)

    def test_cart_update_zero_deletes(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        self.client.post(f"{self.prefix}/cart/update/{ci.id}/", {"quantity": 0})
        self.assertFalse(CartItem.objects.filter(pk=ci.pk).exists())

    def test_cart_remove(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        self.client.post(f"{self.prefix}/cart/remove/{ci.id}/")
        self.assertFalse(CartItem.objects.filter(pk=ci.pk).exists())

    def test_cart_update_requires_post(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        resp = self.client.get(f"{self.prefix}/cart/update/{ci.id}/")
        self.assertEqual(resp.status_code, 405)

    def test_cart_remove_requires_post(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        resp = self.client.get(f"{self.prefix}/cart/remove/{ci.id}/")
        self.assertEqual(resp.status_code, 405)

    def test_cart_notes_persist(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        ci = CartItem.objects.create(
            table_session=session, menu_item=self.fries, quantity=1
        )
        self.client.post(
            f"{self.prefix}/cart/update/{ci.id}/",
            {"notes": "no salt please"},
        )
        ci.refresh_from_db()
        self.assertEqual(ci.notes, "no salt please")

    def test_cart_notes_copied_to_order(self):
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        CartItem.objects.create(
            table_session=session,
            menu_item=self.fries,
            quantity=2,
            notes="extra crispy",
        )
        resp = self.client.post(f"{self.prefix}/cart/send/")
        self.assertEqual(resp.status_code, 302)
        order = Order.objects.filter(table_session=session).first()
        self.assertIsNotNone(order)
        order_item = order.items.first()
        self.assertEqual(order_item.notes, "extra crispy")


class TestCartSend(BaseTestCase):
    def test_cart_send_creates_order_and_empties_cart(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        CartItem.objects.create(table_session=session, menu_item=self.fries, quantity=2)
        resp = self.client.post(f"{self.prefix}/cart/send/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(session.cart_items.count(), 0)
        order = Order.objects.get(table_session=session)
        self.assertEqual(order.status, "pending")
        oi = order.items.get()
        self.assertEqual(oi.price_at_order, self.fries.price)

    def test_cart_send_empty_cart_redirects(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        resp = self.client.post(f"{self.prefix}/cart/send/")
        self.assertRedirects(resp, f"{self.prefix}/cart/", fetch_redirect_response=False)

    def test_cart_send_sets_awaiting_payment(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        CartItem.objects.create(table_session=session, menu_item=self.burger, quantity=1)
        self.client.post(f"{self.prefix}/cart/send/")
        session.refresh_from_db()
        self.assertEqual(session.status, "awaiting_payment")


class TestGetActiveSessionUniqueness(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(name="R", slug="r")
        cls.table = Table.objects.create(restaurant=cls.restaurant, number=1)

    def test_concurrent_creation_yields_single_active_session(self):
        from django.db import IntegrityError, transaction
        from resturant.utils import get_active_session

        s1, _ = TableSession.objects.get_or_create(
            table=self.table,
            status="ordering",
            defaults={"restaurant": self.restaurant},
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TableSession.objects.create(
                    table=self.table, restaurant=self.restaurant, status="ordering"
                )
        fetched_table, fetched_session = get_active_session(
            self.restaurant.slug, self.table.qr_token
        )
        self.assertEqual(fetched_session.pk, s1.pk)


class TestRequirePostGuards(BaseTestCase):
    def test_request_bill_get_does_not_set_flag(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        order = Order.objects.create(table_session=session, status="pending")
        resp = self.client.get(f"{self.prefix}/request-bill/")
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertFalse(order.bill_requested)

    def test_request_bill_post_sets_flag(self):
        session, _ = TableSession.objects.get_or_create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        order = Order.objects.create(table_session=session, status="pending")
        resp = self.client.post(f"{self.prefix}/request-bill/")
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.bill_requested)

    def test_advance_order_status_requires_post(self):
        order = Order.objects.create(
            table_session=TableSession.objects.create(
                table=self.table, restaurant=self.restaurant, status="ordering"
            ),
            status="pending",
        )
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.get(f"/kitchen/order/{order.id}/status/")
        self.assertEqual(resp.status_code, 405)

    def test_mark_table_orders_ready_requires_post(self):
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.get(f"/kitchen/table/{self.table.id}/mark-ready/")
        self.assertEqual(resp.status_code, 405)

    def test_mark_ready_keeps_order_and_hides_from_live_board(self):
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        order = Order.objects.create(table_session=session, status="preparing")
        self.client.login(username="kitchen", password="testpass123")

        resp = self.client.post(
            f"/kitchen/table/{self.table.id}/mark-ready/", follow=True
        )
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, "ready")
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

        board = self.client.get("/kitchen/dashboard/")
        self.assertEqual(board.status_code, 200)
        self.assertEqual(board.context["live_ticket_count"], 0)
        self.assertEqual(board.context["orders"].count(), 0)

    def test_close_table_requires_post(self):
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.get(f"/table/{self.table.id}/close/")
        self.assertEqual(resp.status_code, 405)


class TestKitchenAuthz(BaseTestCase):
    def test_unauthenticated_dashboard_redirects(self):
        resp = self.client.get("/kitchen/dashboard/")
        self.assertRedirects(resp, "/kitchen/login/", fetch_redirect_response=False)

    def test_kitchen_user_cannot_access_analytics(self):
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.get("/dashboard/")
        self.assertRedirects(resp, "/kitchen/dashboard/", fetch_redirect_response=False)

    def test_owner_can_access_analytics(self):
        self.client.login(username="owner", password="testpass123")
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)

    def test_kitchen_can_access_kitchen_dashboard(self):
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.get("/kitchen/dashboard/")
        self.assertEqual(resp.status_code, 200)

    def test_advance_order_status_scoped_to_restaurant(self):
        other_session = TableSession.objects.create(
            table=self.other_table, restaurant=self.other_restaurant, status="ordering"
        )
        other_order = Order.objects.create(
            table_session=other_session, status="pending"
        )
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.post(
            f"/kitchen/order/{other_order.id}/status/",
            {"status": "preparing"},
        )
        self.assertEqual(resp.status_code, 404)
        other_order.refresh_from_db()
        self.assertEqual(other_order.status, "pending")


class TestOrderStatusTransition(BaseTestCase):
    def test_full_transition(self):
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        order = Order.objects.create(table_session=session, status="pending")
        self.client.login(username="kitchen", password="testpass123")

        resp = self.client.post(
            f"/kitchen/order/{order.id}/status/",
            {"status": "preparing"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "preparing")
        self.assertIsNotNone(order.started_preparing_at)

        resp = self.client.post(
            f"/kitchen/order/{order.id}/status/",
            {"status": "ready"},
            follow=True,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "ready")

        resp = self.client.post(
            f"/kitchen/order/{order.id}/status/",
            {"status": "served"},
            follow=True,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "served")

    def test_orderstatus_refresh_served_header(self):
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        Order.objects.create(table_session=session, status="served")
        resp = self.client.get(f"{self.prefix}/orderstatus/refresh/")
        self.assertEqual(resp["X-All-Served"], "1")

    def test_orderstatus_refresh_not_served_header(self):
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        Order.objects.create(table_session=session, status="preparing")
        resp = self.client.get(f"{self.prefix}/orderstatus/refresh/")
        self.assertEqual(resp["X-All-Served"], "0")


class TestCloseTableCreatesBill(BaseTestCase):
    def test_close_creates_paid_bill_and_marks_orders(self):
        self.client.login(username="kitchen", password="testpass123")
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        order = Order.objects.create(table_session=session, status="served")
        OrderItem.objects.create(
            order=order, menu_item=self.fries, quantity=2, price_at_order=self.fries.price
        )

        resp = self.client.post(f"/table/{self.table.id}/close/", follow=True)
        self.assertEqual(resp.status_code, 200)

        session.refresh_from_db()
        self.assertEqual(session.status, "closed")
        self.assertFalse(session.is_active)
        self.assertIsNotNone(session.closed_at)
        order.refresh_from_db()
        self.assertTrue(order.paid)

        bill = Bill.objects.get(table_session=session)
        self.assertTrue(bill.is_paid)
        self.assertEqual(bill.amount, self.fries.price * 2)

    def test_close_after_mark_ready_bills_correct_amount(self):
        # Regression: mark-ready used to delete ready orders (and their items),
        # which made close_table_session produce a zero bill.
        self.client.login(username="kitchen", password="testpass123")
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        order = Order.objects.create(table_session=session, status="preparing")
        OrderItem.objects.create(
            order=order, menu_item=self.fries, quantity=2, price_at_order=self.fries.price
        )
        OrderItem.objects.create(
            order=order, menu_item=self.burger, quantity=1, price_at_order=self.burger.price
        )

        self.client.post(f"/kitchen/table/{self.table.id}/mark-ready/")
        order.refresh_from_db()
        self.assertEqual(order.status, "ready")

        self.client.post(f"/table/{self.table.id}/close/")

        bill = Bill.objects.get(table_session=session)
        self.assertTrue(bill.is_paid)
        self.assertEqual(bill.amount, self.fries.price * 2 + self.burger.price)

    def test_double_close_idempotent(self):
        self.client.login(username="kitchen", password="testpass123")
        session = TableSession.objects.create(
            table=self.table, restaurant=self.restaurant, status="ordering"
        )
        Order.objects.create(table_session=session, status="served")

        self.client.post(f"/table/{self.table.id}/close/")
        session.refresh_from_db()
        self.assertEqual(session.status, "closed")

        # second close on already-closed session (no active session found)
        resp = self.client.post(f"/table/{self.table.id}/close/")
        self.assertEqual(resp.status_code, 302)


class TestLogout(BaseTestCase):
    def test_logout_logs_out(self):
        self.client.login(username="kitchen", password="testpass123")
        resp = self.client.post("/kitchen/logout/", follow=True)
        self.assertRedirects(resp, "/kitchen/login/", fetch_redirect_response=False)

    def test_logout_requires_post(self):
        resp = self.client.get("/kitchen/logout/")
        self.assertEqual(resp.status_code, 405)


class TestManagementDashboardFilters(BaseTestCase):
    def _place(self, days_ago, menu_item=None, qty=1):
        session = TableSession.objects.create(
            table=self.table,
            restaurant=self.restaurant,
            status="closed",
            is_active=False,
        )
        item = menu_item or self.fries
        order = Order.objects.create(table_session=session, status="served")
        OrderItem.objects.create(
            order=order, menu_item=item, quantity=qty, price_at_order=item.price
        )
        Order.objects.filter(pk=order.pk).update(
            placed_at=timezone.now() - timedelta(days=days_ago)
        )
        return order

    def _login_owner(self):
        self.client.login(username="owner", password="testpass123")

    def test_default_weekly_windows_kpis(self):
        self._place(days_ago=0)
        self._place(days_ago=10, menu_item=self.burger)
        self._login_owner()
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_orders"], 1)
        self.assertEqual(resp.context["total_revenue"], self.fries.price)
        self.assertEqual(resp.context["active_range"], "weekly")
        self.assertEqual(len(resp.context["weekly_sales"]), 7)

    def test_today_range_counts_only_today(self):
        self._place(days_ago=0)
        self._place(days_ago=1, menu_item=self.burger)
        self._login_owner()

        resp = self.client.get("/dashboard/?range=today")
        self.assertEqual(resp.context["total_orders"], 1)
        self.assertEqual(resp.context["total_revenue"], self.fries.price)
        # hourly buckets for the current day
        self.assertEqual(len(resp.context["weekly_sales"]), 24)

        resp = self.client.get("/dashboard/?range=weekly")
        self.assertEqual(resp.context["total_orders"], 2)

    def test_monthly_range_series_length(self):
        self._place(days_ago=0)
        self._login_owner()
        resp = self.client.get("/dashboard/?range=monthly")
        self.assertEqual(len(resp.context["weekly_sales"]), 30)

    def test_custom_range(self):
        self._place(days_ago=0)
        self._place(days_ago=20, menu_item=self.burger)
        self._login_owner()
        start = (timezone.now() - timedelta(days=10)).date()
        end = timezone.now().date()
        resp = self.client.get(
            f"/dashboard/?range=custom&from={start.isoformat()}&to={end.isoformat()}"
        )
        self.assertEqual(resp.context["active_range"], "custom")
        self.assertEqual(resp.context["total_orders"], 1)
        self.assertEqual(len(resp.context["weekly_sales"]), (end - start).days + 1)

    def test_invalid_range_falls_back_to_weekly(self):
        self._place(days_ago=0)
        self._place(days_ago=20, menu_item=self.burger)
        self._login_owner()
        resp = self.client.get("/dashboard/?range=banana")
        self.assertEqual(resp.context["active_range"], "weekly")
        self.assertEqual(resp.context["total_orders"], 1)

    def test_reversed_custom_range_falls_back_to_weekly(self):
        self._place(days_ago=0)
        self._login_owner()
        start = timezone.now().date()
        end = (timezone.now() - timedelta(days=10)).date()
        resp = self.client.get(
            f"/dashboard/?range=custom&from={start.isoformat()}&to={end.isoformat()}"
        )
        self.assertEqual(resp.context["active_range"], "weekly")

    def test_search_q_filters_best_sellers_and_recent_orders(self):
        fries_order = self._place(days_ago=0)
        self._place(days_ago=0, menu_item=self.burger)
        self._login_owner()

        resp = self.client.get("/dashboard/?q=fries")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["query"], "fries")
        sellers = list(
            resp.context["best_sellers"].values_list("menu_item__name", flat=True)
        )
        self.assertEqual(sellers, ["Fries"])
        recent_ids = list(resp.context["recent_orders"].values_list("id", flat=True))
        self.assertEqual(recent_ids, [fries_order.id])

    def test_no_query_shows_all_sellers(self):
        self._place(days_ago=0)
        self._place(days_ago=0, menu_item=self.burger)
        self._login_owner()
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.context["query"], "")
        sellers = list(
            resp.context["best_sellers"].values_list("menu_item__name", flat=True)
        )
        self.assertCountEqual(sellers, ["Fries", "Burger"])

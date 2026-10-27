from django.shortcuts import get_object_or_404, redirect
from django.conf import settings
from .models import Restaurant


class SubdomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Health probes must not touch the database: they arrive every few
        # seconds on deployed hosts and can exhaust the connection pooler.
        if request.path == "/health":
            request.restaurant = None
            return self.get_response(request)

        host = request.get_host().split(":")[0]

        if host in ("localhost", "127.0.0.1", ""):
            slug = request.GET.get("r") or request.session.get("restaurant_slug")
            if slug:
                try:
                    request.restaurant = Restaurant.objects.get(slug=slug, is_active=True)
                    request.session["restaurant_slug"] = slug
                except Restaurant.DoesNotExist:
                    request.restaurant = None
            else:
                request.restaurant = Restaurant.objects.filter(is_active=True).first()
                if request.restaurant:
                    request.session["restaurant_slug"] = request.restaurant.slug
        else:
            # Restaurants are addressed by the first host label, e.g.
            #   tastyqueen.example.com -> slug "tastyqueen"
            #   tastyqueen.com         -> slug "tastyqueen"
            # On a shared platform domain (e.g. <app>.onrender.com) there is no
            # per-restaurant subdomain, so fall back to the first active
            # restaurant rather than rendering the page with no branding.
            candidate = host.split(".")[0]
            restaurant = None
            if candidate and candidate != "www":
                restaurant = Restaurant.objects.filter(slug=candidate, is_active=True).first()
            request.restaurant = restaurant or Restaurant.objects.filter(is_active=True).first()

        response = self.get_response(request)
        return response

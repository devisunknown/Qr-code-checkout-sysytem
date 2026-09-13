from django.shortcuts import get_object_or_404, redirect
from django.conf import settings
from .models import Restaurant


class SubdomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
            base_domain = ".".join(host.split(".")[-2:])
            subdomain = host.replace("." + base_domain, "").replace(base_domain, "").strip(".")
            if subdomain and subdomain != "www":
                try:
                    request.restaurant = Restaurant.objects.get(slug=subdomain, is_active=True)
                except Restaurant.DoesNotExist:
                    request.restaurant = None
            else:
                request.restaurant = Restaurant.objects.filter(is_active=True).first()

        response = self.get_response(request)
        return response

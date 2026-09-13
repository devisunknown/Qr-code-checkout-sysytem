def restaurant_context(request):
    return {"restaurant": getattr(request, "restaurant", None)}

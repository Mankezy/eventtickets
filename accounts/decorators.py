"""Rol asosidagi ruxsat dekoratorlari — barcha tekshiruvlar backendda."""
from functools import wraps

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def role_required(*roles, message="Bu sahifaga kirish uchun ruxsatingiz yo'q."):
    """Berilgan rollardan biriga ega foydalanuvchilarni o'tkazadi."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect("login")
            allowed = set(roles)
            ok = user.role in allowed or user.is_superuser
            # Admin barcha rollarga ega
            if "admin" in allowed and user.is_admin_role:
                ok = True
            if not ok:
                return HttpResponseForbidden(message)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def organizer_required(view_func):
    return role_required("organizer", "admin")(view_func)


def controller_required(view_func):
    return role_required("controller", "admin")(view_func)


def admin_required(view_func):
    return role_required("admin")(view_func)

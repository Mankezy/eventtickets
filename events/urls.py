from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("events/", views.event_list, name="event_list"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    # Tashkilotchi
    path("organizer/", views.organizer_dashboard, name="organizer_dashboard"),
    path("organizer/events/new/", views.event_create, name="event_create"),
    path("organizer/events/<int:pk>/edit/", views.event_update, name="event_update"),
    path("organizer/events/<int:event_pk>/ticket-types/new/", views.tickettype_create, name="tickettype_create"),
    path("organizer/ticket-types/<int:pk>/edit/", views.tickettype_update, name="tickettype_update"),
    path("organizer/events/<int:pk>/sales/", views.event_sales, name="event_sales"),
    # Administrator
    path("admin-panel/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/events/<int:pk>/status/", views.admin_event_status, name="admin_event_status"),
    path("admin-panel/users/<int:pk>/role/", views.admin_user_role, name="admin_user_role"),
]

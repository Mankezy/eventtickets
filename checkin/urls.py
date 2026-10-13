from django.urls import path

from . import views

urlpatterns = [
    path("", views.scan_page, name="scan_page"),
    path("event/<int:event_pk>/", views.scan_page, name="scan_page_event"),
    path("verify/<int:event_pk>/", views.verify, name="verify_ticket"),
]

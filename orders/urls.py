from django.urls import path

from . import views

urlpatterns = [
    path("create/<int:event_pk>/", views.order_create, name="order_create"),
    path("<int:pk>/confirm/", views.order_confirm, name="order_confirm"),
    path("<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("<int:pk>/payment/", views.payment, name="payment"),
    path("<int:pk>/payment/process/", views.payment_process, name="payment_process"),
    path("<int:pk>/result/<str:result>/", views.payment_result, name="payment_result"),
    path("my/", views.my_tickets, name="my_tickets"),
    path("ticket/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("ticket/<int:pk>/pdf/", views.ticket_pdf, name="ticket_pdf"),
]

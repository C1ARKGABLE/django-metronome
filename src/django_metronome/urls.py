from django.urls import path

from . import views

urlpatterns = [
    path("", views.hello, name="hello"),
    path(
        "sync/customers/<str:customer_id>/",
        views.sync_customer,
        name="sync_customer",
    ),
]

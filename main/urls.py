from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("links/", views.links, name="links"),
    path("contact/", views.contact, name="contact"),
    path(
        "contact/verify/<uuid:token>/",
        views.verify_contact,
        name="verify_contact",
    ),
]

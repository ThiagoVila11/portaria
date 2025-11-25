from django.urls import path
from django.contrib.auth import views as auth_views
from .views import logout_then_login
from rest_framework import routers

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html",
                                                 redirect_authenticated_user=True,),
                                                name="login",
    ),
    path("logout/", logout_then_login, name="logout"),
]

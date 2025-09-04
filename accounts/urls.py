from django.urls import path
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html",
                                                 redirect_authenticated_user=True,),
                                                name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="login"),  # volta pro login
        name="logout",
    ),
]

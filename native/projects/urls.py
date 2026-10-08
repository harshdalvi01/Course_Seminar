from django.urls import path
# pyrefly: ignore [missing-import]
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
]

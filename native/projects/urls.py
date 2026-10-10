from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('create/', views.project_create_view, name='project_create'),
    path('<int:pk>/', views.project_detail_view, name='project_detail'),
    path('<int:pk>/edit/', views.project_update_view, name='project_update'),
    path('<int:pk>/delete/', views.project_delete_view, name='project_delete'),
]

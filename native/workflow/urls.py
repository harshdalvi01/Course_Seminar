from django.urls import path
from . import views

urlpatterns = [
    path('projects/<int:project_id>/stage/<str:stage>/', views.stage_detail_view, name='stage_detail'),
    path('artifacts/<int:artifact_id>/edit/', views.artifact_edit_view, name='artifact_edit'),
    path('artifacts/<int:artifact_id>/review/', views.artifact_review_view, name='artifact_review'),
]

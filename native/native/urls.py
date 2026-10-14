"""
URL configuration for native project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

def home_view(request):
    try:
        from projects.models import Project
        from workflow.models import Artifact, Review
        total_projects = Project.objects.count()
        total_artifacts = Artifact.objects.count()
        total_reviews = Review.objects.count()
        recent_projects = list(Project.objects.order_by('-created_at')[:4])
    except Exception:
        total_projects = 0
        total_artifacts = 0
        total_reviews = 0
        recent_projects = []
        
    return render(request, 'home.html', {
        'total_projects': total_projects,
        'total_artifacts': total_artifacts,
        'total_reviews': total_reviews,
        'recent_projects': recent_projects,
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('auth/', include('authentication.urls')),
    path('projects/', include('projects.urls')),
    path('workflow/', include('workflow.urls')),
    path('ai/', include('AI.urls')),
]

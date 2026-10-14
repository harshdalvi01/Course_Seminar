from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from .models import Project
from .forms import ProjectForm

@login_required
def dashboard_view(request):
    # Base queryset for current user
    qs = Project.objects.filter(owner=request.user)
    
    # Calculate stats
    total_projects = qs.count()
    active_projects = qs.filter(status='ACTIVE').count()
    completed_projects = qs.filter(status='COMPLETED').count()
    
    # Search
    search_query = request.GET.get('q', '')
    if search_query:
        qs = qs.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))
        
    # Filter
    stage_filter = request.GET.get('stage', '')
    if stage_filter:
        qs = qs.filter(current_stage=stage_filter)
        
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
        
    context = {
        'projects': qs,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'search_query': search_query,
        'stage_filter': stage_filter,
        'status_filter': status_filter,
        'stages': Project.STAGE_CHOICES,
        'statuses': Project.STATUS_CHOICES,
    }
    return render(request, 'projects/dashboard.html', context)

@login_required
def project_create_view(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.save()
            messages.success(request, 'Project created successfully.')
            return redirect('project_detail', pk=project.pk)
    else:
        form = ProjectForm()
    return render(request, 'projects/project_form.html', {'form': form, 'action': 'Create'})

@login_required
def project_detail_view(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    stages = [s[0] for s in Project.STAGE_CHOICES]
    current_index = stages.index(project.current_stage) if project.current_stage in stages else 0
    
    completion_summary = None
    if project.status == 'COMPLETED' or project.current_stage == 'COMPLETED':
        summary_artifacts = []
        for s_key, s_name in [('REQUIREMENTS', 'Requirements'), ('DESIGN', 'Design'), ('CODE', 'Code'), ('TESTING', 'Testing'), ('DEPLOYMENT', 'Deployment')]:
            appr = project.artifacts.filter(stage=s_key, is_approved=True).order_by('-version').first()
            summary_artifacts.append({
                'stage': s_key,
                'stage_name': s_name,
                'artifact': appr,
            })
        completion_summary = {
            'is_completed': True,
            'artifacts': summary_artifacts,
        }
        
    sdlc_stages = ['REQUIREMENTS', 'DESIGN', 'CODE', 'TESTING', 'DEPLOYMENT']
    stage_display_names = dict(Project.STAGE_CHOICES)
    pipeline_info = []
    for s in sdlc_stages:
        approved_art = project.artifacts.filter(stage=s, is_approved=True).order_by('-version').first()
        has_any_art = project.artifacts.filter(stage=s).exists()
        pipeline_info.append({
            'stage': s,
            'name': stage_display_names.get(s, s),
            'is_approved': approved_art is not None,
            'approved_version': approved_art.version if approved_art else None,
            'is_current': (project.current_stage == s and project.status != 'COMPLETED'),
            'has_artifacts': has_any_art,
        })
        
    context = {
        'project': project,
        'stages': stages,
        'current_index': current_index,
        'completion_summary': completion_summary,
        'pipeline_info': pipeline_info,
    }
    return render(request, 'projects/project_detail.html', context)

@login_required
def project_update_view(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated successfully.')
            return redirect('project_detail', pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'projects/project_form.html', {'form': form, 'action': 'Edit', 'project': project})

@login_required
def project_delete_view(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if request.method == 'POST':
        project.delete()
        messages.success(request, 'Project deleted successfully.')
        return redirect('dashboard')
    return render(request, 'projects/project_confirm_delete.html', {'project': project})

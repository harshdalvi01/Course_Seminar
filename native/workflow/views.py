from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Max
from projects.models import Project
from .models import Artifact, Review
from .forms import ArtifactEditForm, ReviewForm

@login_required
def stage_detail_view(request, project_id, stage):
    project = get_object_or_404(Project, pk=project_id, owner=request.user)
    
    # Ensure valid stage
    valid_stages = dict(Project.STAGE_CHOICES)
    if stage not in valid_stages:
        return redirect('project_detail', pk=project.pk)
        
    if request.method == 'POST' and request.POST.get('create_dummy'):
        Artifact.objects.create(
            project=project,
            stage=stage,
            version=1,
            content=f"Initial draft for {valid_stages[stage]}.\n\n(Generated manually for testing).",
            created_by=request.user,
            source_type='HUMAN',
            is_approved=False
        )
        messages.success(request, 'Draft artifact created.')
        return redirect('stage_detail', project_id=project.pk, stage=stage)
        
    artifacts = Artifact.objects.filter(project=project, stage=stage).order_by('-version')
    latest_artifact = artifacts.first() if artifacts.exists() else None
    
    review_form = ReviewForm()
    
    context = {
        'project': project,
        'stage': stage,
        'stage_name': valid_stages[stage],
        'artifacts': artifacts,
        'latest_artifact': latest_artifact,
        'review_form': review_form,
    }
    return render(request, 'workflow/stage_detail.html', context)

@login_required
def artifact_edit_view(request, artifact_id):
    artifact = get_object_or_404(Artifact, pk=artifact_id, project__owner=request.user)
    
    if request.method == 'POST':
        form = ArtifactEditForm(request.POST)
        if form.is_valid():
            # Rule 1: Never overwrite. Rule 3: Every human edit creates a new version.
            new_content = form.cleaned_data['content']
            latest_version = Artifact.objects.filter(project=artifact.project, stage=artifact.stage).aggregate(Max('version'))['version__max'] or 0
            
            new_artifact = Artifact.objects.create(
                project=artifact.project,
                stage=artifact.stage,
                version=latest_version + 1,
                content=new_content,
                created_by=request.user,
                source_type='HUMAN',
                is_approved=False
            )
            
            # Record the EDIT review action on the old artifact to track why a new one was made
            Review.objects.create(
                artifact=artifact,
                reviewer=request.user,
                action='EDIT',
                feedback="Manually edited to create new version."
            )
            
            messages.success(request, 'New version created from your edits.')
            return redirect('stage_detail', project_id=artifact.project.pk, stage=artifact.stage)
    else:
        form = ArtifactEditForm(initial={'content': artifact.content})
        
    context = {
        'artifact': artifact,
        'form': form,
    }
    return render(request, 'workflow/artifact_edit.html', context)

@login_required
def artifact_review_view(request, artifact_id):
    artifact = get_object_or_404(Artifact, pk=artifact_id, project__owner=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        feedback = request.POST.get('feedback', '')
        
        if action in ['REJECT', 'REGENERATE'] and not feedback.strip():
            messages.error(request, f'Feedback is required when choosing {action}.')
            return redirect('stage_detail', project_id=artifact.project.pk, stage=artifact.stage)
            
        # Create review
        Review.objects.create(
            artifact=artifact,
            reviewer=request.user,
            action=action,
            feedback=feedback
        )
        
        if action == 'APPROVE':
            artifact.is_approved = True
            artifact.save()
            # Advance project stage logic (simplified for now)
            stages = [s[0] for s in Project.STAGE_CHOICES]
            try:
                current_idx = stages.index(artifact.project.current_stage)
                stage_idx = stages.index(artifact.stage)
                # Only advance if we are approving the current active stage
                if current_idx == stage_idx and current_idx < len(stages) - 1:
                    artifact.project.current_stage = stages[current_idx + 1]
                    artifact.project.save()
            except ValueError:
                pass
            messages.success(request, 'Artifact approved! Project stage advanced.')
            
        elif action == 'REJECT':
            messages.warning(request, 'Artifact rejected. Please wait for regeneration or edit manually.')
            
        elif action == 'REGENERATE':
            # In the future, this will trigger the Groq agent.
            # For now, just record the review.
            messages.info(request, 'Regeneration requested. (AI generation not yet implemented)')
            
    return redirect('stage_detail', project_id=artifact.project.pk, stage=artifact.stage)

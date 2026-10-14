import logging
from typing import Optional
from django.db import transaction
from django.db.models import Max
from django.contrib.auth.models import User

from projects.models import Project
from workflow.models import Artifact, Review
from ai_services.agents import RequirementAgent, DesignAgent, CodingAgent, TestingAgent, DeploymentAgent

logger = logging.getLogger(__name__)

# Map stages to their respective intelligent agents
AGENT_MAP = {
    'REQUIREMENTS': RequirementAgent,
    'DESIGN': DesignAgent,
    'CODE': CodingAgent,
    'TESTING': TestingAgent,
    'DEPLOYMENT': DeploymentAgent,
}

class HITLServiceError(Exception):
    pass

class HITLService:
    """
    Reusable Human-In-The-Loop Workflow Service.
    Enforces all governance rules and ensures database consistency during SDLC transitions.
    """

    def generate_initial_artifact(self, project: Project, stage: str, requester: User) -> Artifact:
        """Triggers the initial generation of an artifact for a specific stage."""
        agent_class = AGENT_MAP.get(stage)
        if not agent_class:
            raise HITLServiceError(f"No AI Agent configured for stage: {stage}")
            
        agent = agent_class()
        
        # Network call executes outside the transaction to prevent database locks
        try:
            result = agent.execute(project)
        except Exception as e:
            raise HITLServiceError(f"AI Error: {str(e)}")
            
        with transaction.atomic():
            latest_v = Artifact.objects.filter(project=project, stage=stage).aggregate(Max('version'))['version__max'] or 0
            new_artifact = Artifact.objects.create(
                project=project, stage=stage, version=latest_v + 1,
                content=result['content'], created_by=requester, source_type='AI',
                is_approved=False, validation_meta=result['validation']
            )
        return new_artifact

    @transaction.atomic
    def approve_artifact(self, artifact: Artifact, reviewer: User, feedback: str = "") -> Artifact:
        """Approves the artifact and automatically advances the project stage."""
        Review.objects.create(artifact=artifact, reviewer=reviewer, action='APPROVE', feedback=feedback)
        
        artifact.is_approved = True
        artifact.save()
        
        stages = [s[0] for s in Project.STAGE_CHOICES]
        try:
            current_idx = stages.index(artifact.project.current_stage)
            stage_idx = stages.index(artifact.stage)
            # Only advance if we are approving the currently active stage
            if current_idx == stage_idx and current_idx < len(stages) - 1:
                next_stage = stages[current_idx + 1]
                artifact.project.current_stage = next_stage
                if next_stage == 'COMPLETED' or artifact.stage == 'DEPLOYMENT':
                    artifact.project.status = 'COMPLETED'
                    artifact.project.current_stage = 'COMPLETED'
                artifact.project.save()
            elif artifact.stage == 'DEPLOYMENT':
                artifact.project.current_stage = 'COMPLETED'
                artifact.project.status = 'COMPLETED'
                artifact.project.save()
        except ValueError:
            pass
            
        return artifact

    @transaction.atomic
    def edit_artifact(self, artifact: Artifact, editor: User, new_content: str) -> Artifact:
        """Creates a new version of the artifact manually, preserving history."""
        Review.objects.create(artifact=artifact, reviewer=editor, action='EDIT', feedback="Manually edited to create new version.")
        
        latest_v = Artifact.objects.filter(project=artifact.project, stage=artifact.stage).aggregate(Max('version'))['version__max'] or 0
        
        new_artifact = Artifact.objects.create(
            project=artifact.project,
            stage=artifact.stage,
            version=latest_v + 1,
            content=new_content,
            created_by=editor,
            source_type='HUMAN',
            is_approved=False,
            validation_meta=None # Manual edits reset Jev validation status
        )
        return new_artifact

    @transaction.atomic
    def reject_artifact(self, artifact: Artifact, reviewer: User, feedback: str) -> Artifact:
        """Rejects the artifact, demanding a reason from the human reviewer."""
        if not feedback or not feedback.strip():
            raise HITLServiceError("Feedback is strictly required to reject an artifact.")
            
        Review.objects.create(artifact=artifact, reviewer=reviewer, action='REJECT', feedback=feedback)
        return artifact

    def regenerate_artifact(self, artifact: Artifact, requester: User, feedback: str) -> Artifact:
        """Passes feedback to the AI agent to generate a fresh version."""
        if not feedback or not feedback.strip():
            raise HITLServiceError("Feedback is strictly required to regenerate an artifact.")
            
        agent_class = AGENT_MAP.get(artifact.stage)
        if not agent_class:
            raise HITLServiceError(f"No AI Agent configured for stage: {artifact.stage}")
            
        agent = agent_class()
        
        # External generation logic occurs safely outside the DB transaction
        try:
            result = agent.execute(artifact.project, feedback=feedback)
        except Exception as e:
            raise HITLServiceError(f"AI Generation Failed: {str(e)}")
            
        with transaction.atomic():
            Review.objects.create(artifact=artifact, reviewer=requester, action='REGENERATE', feedback=feedback)
            latest_v = Artifact.objects.filter(project=artifact.project, stage=artifact.stage).aggregate(Max('version'))['version__max'] or 0
            
            new_artifact = Artifact.objects.create(
                project=artifact.project,
                stage=artifact.stage,
                version=latest_v + 1,
                content=result['content'],
                created_by=requester,
                source_type='AI',
                is_approved=False,
                validation_meta=result['validation']
            )
        return new_artifact

hitl_service = HITLService()

from django.db import models
from django.contrib.auth.models import User
from projects.models import Project

class Artifact(models.Model):
    SOURCE_CHOICES = [
        ('AI', 'AI Generated'),
        ('HUMAN', 'Human Edited'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='artifacts')
    stage = models.CharField(max_length=20, choices=Project.STAGE_CHOICES)
    version = models.PositiveIntegerField(default=1)
    content = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_artifacts')
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='AI')
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'stage', 'version')
        ordering = ['-version']

    def __str__(self):
        return f"{self.project.name} - {self.get_stage_display()} (v{self.version})"

class Review(models.Model):
    ACTION_CHOICES = [
        ('APPROVE', 'Approve'),
        ('EDIT', 'Edit'),
        ('REJECT', 'Reject'),
        ('REGENERATE', 'Regenerate'),
    ]

    artifact = models.ForeignKey(Artifact, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    feedback = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reviewer.username} - {self.action} on {self.artifact}"

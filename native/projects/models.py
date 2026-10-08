from django.db import models
from django.contrib.auth.models import User

class Project(models.Model):
    STAGE_CHOICES = [
        ('IDEA', 'Idea'),
        ('REQUIREMENTS', 'Requirements'),
        ('DESIGN', 'Design'),
        ('CODE', 'Code'),
        ('TESTING', 'Testing'),
        ('DEPLOYMENT', 'Deployment'),
        ('COMPLETED', 'Completed'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('ARCHIVED', 'Archived'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField()
    current_stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='IDEA')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-updated_at']

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from projects.models import Project
from .models import Artifact, Review

class WorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='tester', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='Test Project',
            description='Test Desc',
            current_stage='REQUIREMENTS'
        )
        self.client.login(username='tester', password='password123')

    def test_artifact_creation(self):
        # Create via the dummy post method
        url = reverse('stage_detail', args=[self.project.pk, 'REQUIREMENTS'])
        response = self.client.post(url, {'create_dummy': '1'})
        self.assertEqual(response.status_code, 302)
        
        self.assertEqual(Artifact.objects.count(), 1)
        art = Artifact.objects.first()
        self.assertEqual(art.version, 1)
        self.assertEqual(art.source_type, 'HUMAN')
        self.assertFalse(art.is_approved)

    def test_version_creation_on_edit(self):
        # Create initial artifact
        art1 = Artifact.objects.create(
            project=self.project,
            stage='REQUIREMENTS',
            version=1,
            content='Original content',
            created_by=self.user
        )
        
        # Edit it
        url = reverse('artifact_edit', args=[art1.pk])
        response = self.client.post(url, {'content': 'Updated content'})
        self.assertEqual(response.status_code, 302)
        
        # Should have 2 artifacts now
        self.assertEqual(Artifact.objects.count(), 2)
        art2 = Artifact.objects.get(version=2)
        self.assertEqual(art2.content, 'Updated content')
        
        # Original should be untouched
        art1.refresh_from_db()
        self.assertEqual(art1.content, 'Original content')
        
        # A review should be logged for the edit action
        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.first()
        self.assertEqual(review.action, 'EDIT')

    def test_review_history_and_approve(self):
        art1 = Artifact.objects.create(
            project=self.project,
            stage='REQUIREMENTS',
            version=1,
            content='Original content',
            created_by=self.user
        )
        
        url = reverse('artifact_review', args=[art1.pk])
        
        # Test Reject (requires feedback)
        response = self.client.post(url, {'action': 'REJECT', 'feedback': ''}) # Fails
        self.assertEqual(Review.objects.count(), 0)
        
        response = self.client.post(url, {'action': 'REJECT', 'feedback': 'Bad'}) # Passes
        self.assertEqual(Review.objects.count(), 1)
        
        # Test Approve
        response = self.client.post(url, {'action': 'APPROVE', 'feedback': 'Looks good'})
        self.assertEqual(Review.objects.count(), 2)
        
        art1.refresh_from_db()
        self.assertTrue(art1.is_approved)
        
        # Project should advance
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'DESIGN')

    def test_preservation_of_old_versions(self):
        # Create versions 1, 2, 3
        Artifact.objects.create(project=self.project, stage='REQUIREMENTS', version=1, content='v1')
        Artifact.objects.create(project=self.project, stage='REQUIREMENTS', version=2, content='v2')
        Artifact.objects.create(project=self.project, stage='REQUIREMENTS', version=3, content='v3')
        
        # Detail view should show all in history table
        url = reverse('stage_detail', args=[self.project.pk, 'REQUIREMENTS'])
        response = self.client.get(url)
        
        self.assertContains(response, 'v1')
        self.assertContains(response, 'v2')
        self.assertContains(response, 'v3')

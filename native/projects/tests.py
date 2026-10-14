from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Project

class ProjectTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='password123')
        self.user2 = User.objects.create_user(username='user2', password='password123')
        
        # User 1 projects
        self.project1 = Project.objects.create(owner=self.user1, name='Project 1', description='Desc 1', current_stage='IDEA', status='ACTIVE')
        self.project2 = Project.objects.create(owner=self.user1, name='Test App', description='Desc 2', current_stage='CODE', status='COMPLETED')
        
        # User 2 project
        self.project3 = Project.objects.create(owner=self.user2, name='User 2 Project', description='Secret')

        self.dashboard_url = reverse('dashboard')
        self.create_url = reverse('project_create')

    def test_dashboard_lists_only_own_projects(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project 1')
        self.assertContains(response, 'Test App')
        self.assertNotContains(response, 'User 2 Project') # Should not see user2's project

    def test_search_projects(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(self.dashboard_url, {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test App')
        self.assertNotContains(response, 'Project 1')

    def test_filter_by_stage_and_status(self):
        self.client.login(username='user1', password='password123')
        response = self.client.get(self.dashboard_url, {'stage': 'CODE'})
        self.assertContains(response, 'Test App')
        self.assertNotContains(response, 'Project 1')

        response2 = self.client.get(self.dashboard_url, {'status': 'ACTIVE'})
        self.assertContains(response2, 'Project 1')
        self.assertNotContains(response2, 'Test App')

    def test_create_project(self):
        self.client.login(username='user1', password='password123')
        response = self.client.post(self.create_url, {
            'name': 'New Idea',
            'description': 'A brilliant new app.'
        })
        # Should redirect to detail view
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.filter(owner=self.user1).count(), 3)
        new_proj = Project.objects.get(name='New Idea')
        self.assertEqual(new_proj.current_stage, 'REQUIREMENTS')

    def test_view_own_project(self):
        self.client.login(username='user1', password='password123')
        detail_url = reverse('project_detail', args=[self.project1.pk])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project 1')

    def test_cannot_view_others_project(self):
        self.client.login(username='user1', password='password123')
        detail_url = reverse('project_detail', args=[self.project3.pk])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404) # 404 due to get_object_or_404(..., owner=request.user)

    def test_edit_project(self):
        self.client.login(username='user1', password='password123')
        update_url = reverse('project_update', args=[self.project1.pk])
        response = self.client.post(update_url, {
            'name': 'Project 1 Updated',
            'description': 'New desc'
        })
        self.assertEqual(response.status_code, 302)
        self.project1.refresh_from_db()
        self.assertEqual(self.project1.name, 'Project 1 Updated')

    def test_cannot_edit_others_project(self):
        self.client.login(username='user1', password='password123')
        update_url = reverse('project_update', args=[self.project3.pk])
        response = self.client.post(update_url, {
            'name': 'Hacked',
            'description': 'Hack'
        })
        self.assertEqual(response.status_code, 404)

    def test_delete_project(self):
        self.client.login(username='user1', password='password123')
        delete_url = reverse('project_delete', args=[self.project1.pk])
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.filter(pk=self.project1.pk).count(), 0)

    def test_cannot_delete_others_project(self):
        self.client.login(username='user1', password='password123')
        delete_url = reverse('project_delete', args=[self.project3.pk])
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Project.objects.filter(pk=self.project3.pk).count(), 1)

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('register')
        self.login_url = reverse('login')
        self.logout_url = reverse('logout')
        self.dashboard_url = reverse('dashboard')
        
        # Create a test user for login testing
        self.user = User.objects.create_user(username='testuser', password='testpassword123')

    def test_registration_view_renders(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'authentication/register.html')

    def test_login_view_renders(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'authentication/login.html')

    def test_protected_dashboard_redirects_unauthenticated(self):
        response = self.client.get(self.dashboard_url)
        # Should redirect to login page
        self.assertRedirects(response, f"{self.login_url}?next={self.dashboard_url}")

    def test_successful_login_and_dashboard_access(self):
        login_success = self.client.login(username='testuser', password='testpassword123')
        self.assertTrue(login_success)
        
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'projects/dashboard.html')
        # Check if username is displayed
        self.assertContains(response, 'testuser')

    def test_logout(self):
        self.client.login(username='testuser', password='testpassword123')
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, reverse('home'))
        
        # Try accessing dashboard after logout
        response = self.client.get(self.dashboard_url)
        self.assertRedirects(response, f"{self.login_url}?next={self.dashboard_url}")

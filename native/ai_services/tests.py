from django.test import TestCase
from unittest.mock import patch, Mock
import requests
from .groq_service import GroqService, GroqServiceError

class GroqServiceTests(TestCase):
    def setUp(self):
        self.service = GroqService()
        self.service.api_key = "test_secret_key" # Force a test key so it bypasses the missing key check

    @patch('ai_services.groq_service.requests.post')
    def test_successful_generation(self, mock_post):
        # Mock a successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "This is a clean AI response"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.service.generate("Write a function.")
        self.assertEqual(result, "This is a clean AI response")

    @patch('ai_services.groq_service.requests.post')
    def test_timeout_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
        with self.assertRaisesMessage(GroqServiceError, "The request to Groq API timed out"):
            self.service.generate("Test prompt")

    @patch('ai_services.groq_service.requests.post')
    def test_api_error_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.HTTPError("401 Client Error: Unauthorized")
        with self.assertRaisesMessage(GroqServiceError, "Groq API error: 401 Client Error: Unauthorized"):
            self.service.generate("Test prompt")
            
    def test_missing_api_key(self):
        self.service.api_key = None
        with self.assertRaisesMessage(GroqServiceError, "GROQ_API_KEY is not configured"):
            self.service.generate("Test prompt")

from .jev_service import JevService, JevServiceError

class JevServiceTests(TestCase):
    def setUp(self):
        self.service = JevService()
        self.service.api_key = "test_jev_key"

    @patch('ai_services.jev_service.requests.post')
    def test_successful_validation_and_normalization(self, mock_post):
        mock_response = Mock()
        # Jev might return an unpredictable structure, testing the normalizer's adaptability
        mock_response.json.return_value = {
            "is_valid": True,
            "score": 0.95,
            "errors": ["Line 4 is ambiguous"],
            "warnings": "Syntax looks slightly off",
            "requires_human_review": True
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.service.validate_artifact("Test content", "REQUIREMENTS")
        
        # Check normalized structure
        self.assertTrue(result["valid"])
        self.assertEqual(result["confidence"], 0.95)
        self.assertEqual(result["issues"], ["Line 4 is ambiguous"])
        self.assertEqual(result["warnings"], ["Syntax looks slightly off"])
        self.assertTrue(result["requires_human_review"])

    @patch('ai_services.jev_service.requests.post')
    def test_timeout_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
        with self.assertRaisesMessage(JevServiceError, "The request to Jev API timed out"):
            self.service.validate_artifact("Test", "DESIGN")

    @patch('ai_services.jev_service.requests.post')
    def test_malformed_json_response(self, mock_post):
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        with self.assertRaisesMessage(JevServiceError, "Jev API returned an invalid, non-JSON response"):
            self.service.validate_artifact("Test", "DESIGN")

    @patch('ai_services.jev_service.requests.post')
    def test_api_error_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.HTTPError("500 Server Error")
        with self.assertRaisesMessage(JevServiceError, "Jev API error: 500 Server Error"):
            self.service.validate_artifact("Test", "DESIGN")

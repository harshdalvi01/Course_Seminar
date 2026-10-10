from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch, Mock

from projects.models import Project
from .models import Artifact, Review
from .hitl_service import hitl_service, HITLServiceError

class HITLServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='Test Project',
            description='Test Desc',
            current_stage='REQUIREMENTS'
        )
        self.artifact = Artifact.objects.create(
            project=self.project,
            stage='REQUIREMENTS',
            version=1,
            content='Original content v1',
            created_by=self.user,
            is_approved=False
        )

    def test_approve_artifact_advances_stage(self):
        hitl_service.approve_artifact(self.artifact, self.user, "Looks good")
        
        self.artifact.refresh_from_db()
        self.project.refresh_from_db()
        
        self.assertTrue(self.artifact.is_approved)
        self.assertEqual(self.project.current_stage, 'DESIGN')
        
        review = Review.objects.first()
        self.assertEqual(review.action, 'APPROVE')
        self.assertEqual(review.feedback, "Looks good")

    def test_edit_artifact_preserves_old_version(self):
        new_artifact = hitl_service.edit_artifact(self.artifact, self.user, "Updated content v2")
        
        self.assertEqual(Artifact.objects.count(), 2)
        self.assertEqual(new_artifact.version, 2)
        self.assertEqual(new_artifact.content, "Updated content v2")
        self.assertEqual(new_artifact.source_type, 'HUMAN')
        self.assertFalse(new_artifact.is_approved)
        
        # Verify review trace on the original artifact
        review = Review.objects.first()
        self.assertEqual(review.artifact, self.artifact)
        self.assertEqual(review.action, 'EDIT')

    def test_reject_artifact_requires_feedback(self):
        with self.assertRaises(HITLServiceError):
            hitl_service.reject_artifact(self.artifact, self.user, "")
            
        with self.assertRaises(HITLServiceError):
            hitl_service.reject_artifact(self.artifact, self.user, "   ")
            
        hitl_service.reject_artifact(self.artifact, self.user, "Bad structure.")
        
        self.project.refresh_from_db()
        # Stage remains unchanged
        self.assertEqual(self.project.current_stage, 'REQUIREMENTS')
        
        review = Review.objects.first()
        self.assertEqual(review.action, 'REJECT')

    @patch('workflow.hitl_service.AGENT_MAP')
    def test_regenerate_artifact(self, mock_agent_map):
        mock_agent = Mock()
        mock_agent.execute.return_value = {
            'content': 'AI regenerated content v2',
            'validation': {'valid': True, 'confidence': 0.99, 'requires_human_review': True}
        }
        mock_agent_class = Mock(return_value=mock_agent)
        mock_agent_map.get.return_value = mock_agent_class
        
        # Missing feedback fails
        with self.assertRaises(HITLServiceError):
            hitl_service.regenerate_artifact(self.artifact, self.user, "")
            
        new_artifact = hitl_service.regenerate_artifact(self.artifact, self.user, "Please add more details.")
        
        self.assertEqual(Artifact.objects.count(), 2)
        self.assertEqual(new_artifact.version, 2)
        self.assertEqual(new_artifact.content, "AI regenerated content v2")
        self.assertEqual(new_artifact.source_type, 'AI')
        self.assertIsNotNone(new_artifact.validation_meta)
        
        # Verify trace
        review = Review.objects.first()
        self.assertEqual(review.action, 'REGENERATE')
        self.assertEqual(review.feedback, "Please add more details.")

    @patch('workflow.hitl_service.AGENT_MAP')
    def test_generate_initial_artifact(self, mock_agent_map):
        mock_agent = Mock()
        mock_agent.execute.return_value = {
            'content': 'Initial AI content',
            'validation': {'valid': True}
        }
        mock_agent_class = Mock(return_value=mock_agent)
        mock_agent_map.get.return_value = mock_agent_class
        
        new_artifact = hitl_service.generate_initial_artifact(self.project, 'DESIGN', self.user)
        
        self.assertEqual(new_artifact.stage, 'DESIGN')
        self.assertEqual(new_artifact.version, 1)
        self.assertEqual(new_artifact.source_type, 'AI')

    @patch('ai_services.groq_service.GroqService.generate')
    @patch('ai_services.jev_service.JevService.validate_artifact')
    def test_design_agent_end_to_end_flow(self, mock_validate, mock_generate):
        # 1. We must have approved requirements first
        hitl_service.approve_artifact(self.artifact, self.user, "Requirements look great.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'DESIGN')
        
        # Setup mocks for AI services
        mock_generate.return_value = "AI Design Architecture Content"
        mock_validate.return_value = {
            'valid': True,
            'confidence': 0.88,
            'issues': [],
            'warnings': ["Security module needs expansion"],
            'requires_human_review': True
        }
        
        # 2. Trigger HITL generation of the DESIGN artifact
        design_art = hitl_service.generate_initial_artifact(self.project, 'DESIGN', self.user)
        
        # Verify the agent built the context correctly with the approved requirements
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1]
        self.assertIn("Original content v1", call_kwargs['context']) # Context contains the approved req content
        self.assertIn("Test Desc", call_kwargs['context'])           # Context contains the project idea
        
        # Verify artifact state
        self.assertEqual(design_art.stage, 'DESIGN')
        self.assertEqual(design_art.content, "AI Design Architecture Content")
        self.assertFalse(design_art.is_approved)
        self.assertIsNotNone(design_art.validation_meta)
        self.assertEqual(design_art.validation_meta['confidence'], 0.88)
        
        # 3. Approve the Design
        hitl_service.approve_artifact(design_art, self.user, "Design approved")
        
        # 4. Verify project advanced to CODE
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'CODE')
        
    def test_design_agent_fails_without_approved_requirements(self):
        # artifact is NOT approved initially in setUp
        with self.assertRaisesMessage(HITLServiceError, "AI Error: An approved REQUIREMENTS artifact must exist before generating DESIGN."):
            hitl_service.generate_initial_artifact(self.project, 'DESIGN', self.user)

    @patch('ai_services.groq_service.GroqService.generate')
    @patch('ai_services.jev_service.JevService.validate_artifact')
    def test_coding_agent_end_to_end_flow(self, mock_validate, mock_generate):
        # 1. Setup approved requirements and design
        hitl_service.approve_artifact(self.artifact, self.user, "Approved reqs")
        
        design_art = Artifact.objects.create(
            project=self.project, stage='DESIGN', version=1, content='Design content',
            created_by=self.user, is_approved=False
        )
        hitl_service.approve_artifact(design_art, self.user, "Approved design")
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'CODE')
        
        # 2. Mock generation returning the JSON format
        mock_generate.return_value = '```json\n[{"path": "models.py", "purpose": "schema", "content": "pass"}]\n```'
        mock_validate.return_value = {'valid': True, 'requires_human_review': True}
        
        # 3. Generate CODE
        code_art = hitl_service.generate_initial_artifact(self.project, 'CODE', self.user)
        
        # Verify context built successfully
        call_kwargs = mock_generate.call_args[1]
        self.assertIn("Original content v1", call_kwargs['context']) # Reqs
        self.assertIn("Design content", call_kwargs['context'])      # Design
        
        self.assertEqual(code_art.stage, 'CODE')
        self.assertIn('models.py', code_art.content)
        
        # 4. Approve CODE
        hitl_service.approve_artifact(code_art, self.user, "Code approved")
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'TESTING')

    def test_coding_agent_fails_without_prerequisites(self):
        # Only have approved requirements, no design
        hitl_service.approve_artifact(self.artifact, self.user, "Approved reqs")
        
        with self.assertRaisesMessage(HITLServiceError, "Both approved REQUIREMENTS and DESIGN artifacts must exist before generating CODE."):
            hitl_service.generate_initial_artifact(self.project, 'CODE', self.user)

    @patch('ai_services.groq_service.GroqService.generate')
    @patch('ai_services.jev_service.JevService.validate_artifact')
    def test_testing_agent_end_to_end_flow(self, mock_validate, mock_generate):
        # 1. Setup approved requirements, design, code
        hitl_service.approve_artifact(self.artifact, self.user, "Approved reqs")
        
        design_art = Artifact.objects.create(
            project=self.project, stage='DESIGN', version=1, content='Design content',
            created_by=self.user, is_approved=False
        )
        hitl_service.approve_artifact(design_art, self.user, "Approved design")
        
        code_art = Artifact.objects.create(
            project=self.project, stage='CODE', version=1, content='Code content',
            created_by=self.user, is_approved=False
        )
        hitl_service.approve_artifact(code_art, self.user, "Approved code")
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'TESTING')
        
        # 2. Mock generation
        mock_generate.return_value = "# Test Strategy\nStrategy content"
        mock_validate.return_value = {'valid': True, 'requires_human_review': True}
        
        # 3. Generate TESTING
        test_art = hitl_service.generate_initial_artifact(self.project, 'TESTING', self.user)
        
        # Verify context built successfully with all 3 preceding artifacts
        call_kwargs = mock_generate.call_args[1]
        self.assertIn("Original content v1", call_kwargs['context']) # Reqs
        self.assertIn("Design content", call_kwargs['context'])      # Design
        self.assertIn("Code content", call_kwargs['context'])        # Code
        
        self.assertEqual(test_art.stage, 'TESTING')
        
        # 4. Approve TESTING
        hitl_service.approve_artifact(test_art, self.user, "Testing approved")
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'DEPLOYMENT')

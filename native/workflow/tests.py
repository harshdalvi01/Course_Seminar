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
        import json as _json
        mock_generate.return_value = _json.dumps({
            "testing_summary": {
                "total_test_cases": 2,
                "requirement_coverage_percentage": 100.0,
                "covered_requirements": ["FR-01"],
                "uncovered_requirements": [],
                "total_requirements_count": 1,
                "potential_issues_count": 0,
                "summary_note": "Static analysis only."
            },
            "generated_test_cases": [
                {
                    "id": "TC-01",
                    "scenario": "Verify positive path",
                    "scenario_type": "Positive",
                    "requirement_ref": "FR-01",
                    "expected_result": "Succeeds cleanly",
                    "priority": "High",
                    "status": "Not Executed"
                },
                {
                    "id": "TC-02",
                    "scenario": "Verify invalid payload handling",
                    "scenario_type": "Negative",
                    "requirement_ref": "FR-01",
                    "expected_result": "Returns validation error",
                    "priority": "Medium",
                    "status": "Not Executed"
                }
            ],
            "potential_issues": [],
            "recommendations": []
        })
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

    def test_deployment_agent_fails_without_prerequisites(self):
        # We only have approved requirements in setUp
        hitl_service.approve_artifact(self.artifact, self.user, "Approved reqs")
        
        with self.assertRaisesMessage(HITLServiceError, "Approved REQUIREMENTS, DESIGN, CODE, and TESTING artifacts must exist before generating DEPLOYMENT."):
            hitl_service.generate_initial_artifact(self.project, 'DEPLOYMENT', self.user)

    @patch('ai_services.groq_service.GroqService.generate')
    @patch('ai_services.jev_service.JevService.validate_artifact')
    def test_deployment_agent_end_to_end_flow_and_completion(self, mock_validate, mock_generate):
        # 1. Setup approved requirements, design, code, testing
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
        
        test_art = Artifact.objects.create(
            project=self.project, stage='TESTING', version=1, content='Testing content',
            created_by=self.user, is_approved=False
        )
        hitl_service.approve_artifact(test_art, self.user, "Approved testing")
        
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'DEPLOYMENT')
        self.assertEqual(self.project.status, 'ACTIVE')
        
        # 2. Mock Deployment generation and Jev validation
        import json as _json
        deployment_output = _json.dumps({
            "deployment_recommendation": {
                "hosting_platform": "Render (Managed Web Service)",
                "database_recommendation": "Render PostgreSQL",
                "config_requirements": ["Python 3.11", "HTTPS enforced"],
                "explanation": "Suitable managed PaaS for Python prototypes."
            },
            "deployment_readiness": [
                {"check": "Dependencies", "status": "Needs Review", "explanation": "Confirm requirements.txt."},
                {"check": "Environment Variables", "status": "Needs Review", "explanation": "Configure SECRET_KEY."},
                {"check": "Security", "status": "Needs Review", "explanation": "Ensure DEBUG=False."},
                {"check": "Database", "status": "Ready", "explanation": "SQLite or PostgreSQL configured."},
                {"check": "Static Files", "status": "Needs Review", "explanation": "Configure static serving."}
            ],
            "deployment_instructions": {
                "steps": [
                    "1. Prepare production configuration.",
                    "2. Configure environment variables.",
                    "3. Set up database.",
                    "4. Install dependencies.",
                    "5. Configure static files.",
                    "6. Deploy manually from host dashboard.",
                    "7. Verify application works."
                ],
                "verification_checklist": ["Open live URL in browser."]
            }
        })
        mock_generate.return_value = deployment_output
        mock_validate.return_value = {
            'valid': True,
            'confidence': 0.95,
            'issues': [],
            'warnings': [],
            'requires_human_review': True
        }
        
        # 3. Generate DEPLOYMENT artifact
        deploy_art = hitl_service.generate_initial_artifact(self.project, 'DEPLOYMENT', self.user)
        
        # Verify Groq context received all 4 prerequisites
        call_kwargs = mock_generate.call_args[1]
        self.assertIn("Original content v1", call_kwargs['context']) # Reqs
        self.assertIn("Design content", call_kwargs['context'])      # Design
        self.assertIn("Code content", call_kwargs['context'])        # Code
        self.assertIn("Testing content", call_kwargs['context'])     # Testing
        
        # Verify Jev validation rules were evaluated
        val_rules = mock_validate.call_args[1]['rules']
        self.assertTrue(any('security' in r.lower() for r in val_rules))
        self.assertTrue(any('readiness' in r.lower() for r in val_rules))
        
        self.assertEqual(deploy_art.stage, 'DEPLOYMENT')
        self.assertEqual(deploy_art.version, 1)
        self.assertFalse(deploy_art.is_approved)
        self.assertEqual(deploy_art.validation_meta['confidence'], 0.95)
        
        # 4. Human Approval of the Deployment artifact
        hitl_service.approve_artifact(deploy_art, self.user, "Final deployment approved.")
        
        # 5. Verify status and stage advanced to COMPLETED
        deploy_art.refresh_from_db()
        self.project.refresh_from_db()
        
        self.assertTrue(deploy_art.is_approved)
        self.assertEqual(self.project.current_stage, 'COMPLETED')
        self.assertEqual(self.project.status, 'COMPLETED')
        
        # 6. Verify Completion Summary rendering on Project Detail view
        self.client.force_login(self.user)
        res = self.client.get(reverse('project_detail', kwargs={'pk': self.project.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SDLC Lifecycle Completed")
        self.assertContains(res, "Requirements")
        self.assertContains(res, "Deployment")
        
        # 7. Verify accessing COMPLETED stage in workflow redirects to project detail
        res_completed = self.client.get(reverse('stage_detail', kwargs={'project_id': self.project.pk, 'stage': 'COMPLETED'}))
        self.assertRedirects(res_completed, reverse('project_detail', kwargs={'pk': self.project.pk}))


class DesignDiagramTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='diagram_tester', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='Design Diagram System',
            description='Test App for Diagrams',
            current_stage='DESIGN'
        )
        self.req_artifact = Artifact.objects.create(
            project=self.project,
            stage='REQUIREMENTS',
            version=1,
            content='Approved requirements content for design testing.',
            created_by=self.user,
            is_approved=True
        )
        self.sample_design_markdown = """# System Design Specification

## 1. System Architecture
Client-server architecture on Django.

## 2. Database Design
Relational entities.

# System Design Diagrams

### 1. System Architecture Diagram (Essential)
**Type:** System Architecture Diagram (Essential)
**Status:** Generated
**Description:** High-level component topology illustrating browser client, backend services, and database.
```mermaid
flowchart TD
    Client[Browser Client] --> Backend[Django Server]
    Backend --> DB[(Database)]
```
**Key Observations:** Clean separation of concerns.

### 2. Use Case Diagram (Essential)
**Type:** Use Case Diagram (Essential)
**Status:** Generated
**Description:** Visual actor-to-functionality representation.
```mermaid
flowchart LR
    User([End User]) --> Action[Perform Task]
```

### 3. Entity Relationship Diagram (ERD) (Essential)
**Type:** Entity Relationship Diagram (ERD) (Essential)
**Status:** Generated
**Description:** Relational schema.
```mermaid
erDiagram
    USER ||--o{ TASK : manages
```

### 4. Class Diagram (Recommended)
**Type:** Class Diagram (Recommended)
**Status:** Not Generated
**Description:** Not generated: The approved requirements do not specify sufficient information to model a class diagram without inventing unauthorized information.

### 5. Sequence Diagram (Recommended)
**Type:** Sequence Diagram (Recommended)
**Status:** Generated
**Description:** Chronological request flow.
```mermaid
sequenceDiagram
    User->>Server: Request Data
    Server-->>User: Response
```
"""
        self.design_artifact = Artifact.objects.create(
            project=self.project,
            stage='DESIGN',
            version=1,
            content=self.sample_design_markdown,
            created_by=self.user,
            is_approved=False
        )

    def test_extract_and_validate_all_five_diagrams(self):
        from workflow.utils import extract_design_diagrams, parse_design_doc
        parsed = parse_design_doc(self.sample_design_markdown)
        self.assertIsNotNone(parsed)
        self.assertEqual(len(parsed['diagrams']), 5)
        
        # Verify 3 essential appear first
        essential = parsed['essential_diagrams']
        self.assertEqual(len(essential), 3)
        self.assertEqual(essential[0]['type'], 'system_architecture')
        self.assertEqual(essential[1]['type'], 'use_case')
        self.assertEqual(essential[2]['type'], 'erd')
        
        for d in essential:
            self.assertEqual(d['status'], 'generated')
            self.assertTrue(d['is_valid_syntax'])

        # Verify 2 recommended appear below
        recommended = parsed['recommended_diagrams']
        self.assertEqual(len(recommended), 2)
        self.assertEqual(recommended[0]['type'], 'class_diagram')
        self.assertEqual(recommended[1]['type'], 'sequence_diagram')
        
        # Class diagram should be not_generated with clear explanation
        self.assertEqual(recommended[0]['status'], 'not_generated')
        self.assertIn("not specify sufficient information", recommended[0]['description'])
        
        # Sequence diagram is generated
        self.assertEqual(recommended[1]['status'], 'generated')
        self.assertTrue(recommended[1]['is_valid_syntax'])

    @patch('ai_services.agents.groq_service.generate')
    @patch('ai_services.agents.jev_service.validate_artifact')
    def test_single_diagram_regeneration_creates_v_plus_1(self, mock_validate, mock_generate):
        mock_generate.return_value = """### Class Diagram (Recommended)
**Type:** Class Diagram (Recommended)
**Status:** Generated
**Description:** Regenerated class diagram based on reviewer directives.
```mermaid
classDiagram
    class User {
        +int id
    }
```
**Key Observations:** Now includes user domain model.
"""
        mock_validate.return_value = {
            'valid': True,
            'confidence': 0.95,
            'issues': [],
            'warnings': [],
            'requires_human_review': True
        }

        new_art = hitl_service.regenerate_diagram(
            artifact=self.design_artifact,
            diagram_type='class_diagram',
            requester=self.user,
            feedback='Please model the User domain class.'
        )

        self.assertEqual(new_art.version, 2)
        self.assertEqual(new_art.stage, 'DESIGN')
        self.assertFalse(new_art.is_approved)
        
        # Verify review audit log
        reviews = Review.objects.filter(artifact=self.design_artifact)
        self.assertEqual(reviews.count(), 1)
        self.assertEqual(reviews.first().action, 'REGENERATE')
        self.assertIn('Class Diagram', reviews.first().feedback)

        # Verify the new artifact contains the regenerated class diagram
        self.assertIn("classDiagram", new_art.content)
        self.assertIn("class User", new_art.content)
        
        # And verify that all original sections were preserved
        self.assertIn("System Architecture", new_art.content)
        self.assertIn("Entity Relationship Diagram", new_art.content)

    @patch('ai_services.agents.groq_service.generate')
    @patch('ai_services.agents.jev_service.validate_artifact')
    def test_regenerate_diagram_view_endpoint(self, mock_validate, mock_generate):
        mock_generate.return_value = """### Use Case Diagram (Essential)
**Type:** Use Case Diagram (Essential)
**Status:** Generated
**Description:** Updated use case diagram.
```mermaid
flowchart LR
    Admin([Admin]) --> Manage[Manage System]
```
"""
        mock_validate.return_value = {
            'valid': True,
            'confidence': 0.92,
            'issues': [],
            'warnings': [],
            'requires_human_review': True
        }

        self.client.force_login(self.user)
        url = reverse('regenerate_diagram', kwargs={
            'artifact_id': self.design_artifact.pk,
            'diagram_type': 'use_case'
        })
        response = self.client.post(url, {'feedback': 'Add Admin use cases'})
        
        # Should redirect back to stage_detail
        self.assertRedirects(response, reverse('stage_detail', kwargs={
            'project_id': self.project.pk,
            'stage': 'DESIGN'
        }))
        
        # Check that artifact version 2 was created
        self.assertEqual(Artifact.objects.filter(project=self.project, stage='DESIGN').count(), 2)


class ConsolidatedTestingReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='qa_tester', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='QA Verification Project',
            description='A task manager web app with authentication.',
            current_stage='TESTING'
        )
        # Approved Requirements
        self.req_art = Artifact.objects.create(
            project=self.project, stage='REQUIREMENTS', version=1,
            content='# Functional Requirements\nFR-01: Login\nFR-02: Create Task\nFR-03: Delete Task',
            created_by=self.user, is_approved=True
        )
        # Unapproved newer Requirements v2 should be ignored
        self.req_unapproved = Artifact.objects.create(
            project=self.project, stage='REQUIREMENTS', version=2,
            content='UNAPPROVED DRAFT REQUIREMENT DO NOT USE',
            created_by=self.user, is_approved=False
        )
        # Approved Design
        self.design_art = Artifact.objects.create(
            project=self.project, stage='DESIGN', version=1,
            content='# 1. System Architecture\nDjango backend with SQLite.',
            created_by=self.user, is_approved=True
        )
        # Approved Code
        self.code_art = Artifact.objects.create(
            project=self.project, stage='CODE', version=1,
            content='[{"path": "app/views.py", "purpose": "Views", "content": "def create_task(request): pass"}]',
            created_by=self.user, is_approved=True
        )

    def _valid_sample_json(self, force_passed=False):
        import json
        return json.dumps({
            "testing_summary": {
                "total_test_cases": 3,
                "requirement_coverage_percentage": 99.0,  # deliberately inaccurate to test deterministic recalculation (2/3 = 66.7%)
                "covered_requirements": ["FR-01: Login", "FR-02: Create Task"],
                "uncovered_requirements": ["FR-03: Delete Task"],
                "total_requirements_count": 3,
                "potential_issues_count": 1,
                "summary_note": "Static analysis complete. Unexecuted."
            },
            "generated_test_cases": [
                {
                    "id": "TC-01",
                    "scenario": "User logs in with valid credentials",
                    "scenario_type": "Positive",
                    "requirement_ref": "FR-01",
                    "expected_result": "Redirects to task dashboard",
                    "priority": "High",
                    "status": "Passed" if force_passed else "Not Executed"
                },
                {
                    "id": "TC-02",
                    "scenario": "User logs in with invalid password",
                    "scenario_type": "Negative",
                    "requirement_ref": "FR-01",
                    "expected_result": "Displays invalid login error",
                    "priority": "High",
                    "status": "Not Executed"
                },
                {
                    "id": "TC-03",
                    "scenario": "Create task with valid title",
                    "scenario_type": "Positive",
                    "requirement_ref": "FR-02",
                    "expected_result": "Task saved to database",
                    "priority": "Medium",
                    "status": "Not Executed"
                }
            ],
            "potential_issues": [
                {
                    "id": "ISS-01",
                    "description": "Missing login_required check on create_task view",
                    "severity": "High",
                    "affected_component": "app/views.py",
                    "explanation": "The create_task handler does not enforce authentication.",
                    "analysis_type": "AI Static Analysis (Unverified at Runtime)"
                }
            ],
            "recommendations": [
                {
                    "title": "Enforce View Authentication",
                    "action": "Decorate create_task with @login_required.",
                    "related_ref": "ISS-01"
                },
                {
                    "title": "Add Delete Task Test Coverage",
                    "action": "Add negative and positive cases for FR-03.",
                    "related_ref": "FR-03"
                }
            ]
        })

    @patch('ai_services.agents.groq_service.generate')
    @patch('ai_services.agents.jev_service.validate_artifact')
    def test_testing_agent_uses_only_approved_context_and_enforces_safety(self, mock_validate, mock_generate):
        mock_generate.return_value = self._valid_sample_json(force_passed=True)
        mock_validate.return_value = {
            'valid': True, 'confidence': 0.91, 'issues': [], 'warnings': [], 'requires_human_review': True
        }

        art = hitl_service.generate_initial_artifact(self.project, 'TESTING', self.user)

        # Verify context included approved v1 and excluded unapproved v2
        ctx = mock_generate.call_args[1]['context']
        self.assertIn("FR-01: Login", ctx)
        self.assertIn("app/views.py", ctx)
        self.assertNotIn("UNAPPROVED DRAFT REQUIREMENT DO NOT USE", ctx)

        # Verify Jev received all 5 Testing consistency rules
        rules = mock_validate.call_args[1]['rules']
        self.assertTrue(any("four report sections" in r.lower() for r in rules))
        self.assertTrue(any("not executed" in r.lower() for r in rules))
        self.assertTrue(any("internally consistent" in r.lower() for r in rules))

        # Parse saved artifact & verify safety constraints + deterministic math
        import json
        saved = json.loads(art.content)
        for tc in saved['generated_test_cases']:
            self.assertEqual(tc['status'], 'Not Executed')  # Even though Groq mock said 'Passed', overridden!

        # Math recalculation: 2/3 covered = 66.7%
        self.assertEqual(saved['testing_summary']['requirement_coverage_percentage'], 66.7)
        self.assertEqual(saved['testing_summary']['total_test_cases'], 3)
        self.assertEqual(saved['testing_summary']['potential_issues_count'], 1)

    @patch('ai_services.agents.groq_service.generate')
    def test_malformed_json_response_fails_gracefully_without_saving(self, mock_generate):
        mock_generate.return_value = "Here is my response: {invalid json truncated..."

        with self.assertRaises(HITLServiceError) as cm:
            hitl_service.generate_initial_artifact(self.project, 'TESTING', self.user)

        self.assertIn("Malformed JSON", str(cm.exception))
        self.assertEqual(Artifact.objects.filter(project=self.project, stage='TESTING').count(), 0)

    def test_parse_testing_report_and_stage_ui_rendering(self):
        from workflow.utils import parse_testing_report
        valid_art = Artifact.objects.create(
            project=self.project, stage='TESTING', version=1,
            content=self._valid_sample_json(),
            created_by=self.user, is_approved=False,
            validation_meta={'valid': True, 'confidence': 0.90, 'issues': [], 'warnings': []}
        )

        self.client.force_login(self.user)
        res = self.client.get(reverse('stage_detail', kwargs={'project_id': self.project.pk, 'stage': 'TESTING'}))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, '<h4 class="panel-header-title">Testing Summary</h4>')
        self.assertContains(res, "Generated Test Cases")
        self.assertNotContains(res, '<h4 class="panel-header-title">Potential Issues')
        self.assertNotContains(res, '<h4 class="panel-header-title">Recommendations')
        self.assertContains(res, "Not Executed")
        self.assertContains(res, "TC-01")

        # Verify malformed edit error state
        malformed_parsed = parse_testing_report("{incomplete")
        self.assertFalse(malformed_parsed['is_structured'])
        self.assertIsNotNone(malformed_parsed['parse_error'])

    @patch('ai_services.agents.groq_service.generate')
    @patch('ai_services.agents.jev_service.validate_artifact')
    def test_hitl_lifecycle_and_deployment_gating(self, mock_validate, mock_generate):
        mock_generate.return_value = self._valid_sample_json()
        mock_validate.return_value = {'valid': True, 'confidence': 0.94, 'issues': [], 'warnings': [], 'requires_human_review': True}

        v1 = hitl_service.generate_initial_artifact(self.project, 'TESTING', self.user)

        # Reject v1 without feedback fails
        with self.assertRaises(HITLServiceError):
            hitl_service.reject_artifact(v1, self.user, "")

        # Reject with feedback logs review and does NOT advance stage
        hitl_service.reject_artifact(v1, self.user, "Needs more negative tests.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'TESTING')

        # Deployment cannot run before Testing is approved
        with self.assertRaises(HITLServiceError):
            hitl_service.generate_initial_artifact(self.project, 'DEPLOYMENT', self.user)

        # Edit creates v2
        v2 = hitl_service.edit_artifact(v1, self.user, self._valid_sample_json())
        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.source_type, 'HUMAN')

        # Regenerate creates v3
        v3 = hitl_service.regenerate_artifact(v2, self.user, "Include SQL injection test scenario.")
        self.assertEqual(v3.version, 3)

        # Approve v3 -> advances to DEPLOYMENT
        hitl_service.approve_artifact(v3, self.user, "Consolidated Testing Report Approved.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'DEPLOYMENT')

        # DeploymentAgent uses ONLY approved v3 TESTING artifact
        from ai_services.agents import DeploymentAgent
        dep_ctx = DeploymentAgent().build_context(self.project)
        self.assertIn("TC-01", dep_ctx)


class SimplifiedDeploymentReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='release_tester', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='Task App Release',
            description='Lightweight Django task tracking prototype.',
            current_stage='DEPLOYMENT'
        )
        Artifact.objects.create(
            project=self.project, stage='REQUIREMENTS', version=1,
            content='Approved Requirements v1', created_by=self.user, is_approved=True
        )
        Artifact.objects.create(
            project=self.project, stage='REQUIREMENTS', version=2,
            content='UNAPPROVED DRAFT REQ DO NOT INCLUDE', created_by=self.user, is_approved=False
        )
        Artifact.objects.create(
            project=self.project, stage='DESIGN', version=1,
            content='Approved Design Architecture v1', created_by=self.user, is_approved=True
        )
        # Code files WITHOUT requirements.txt to test dependency evidence guard
        Artifact.objects.create(
            project=self.project, stage='CODE', version=1,
            content='[{"path": "app/views.py", "purpose": "Views", "content": "def index(r): pass"}]',
            created_by=self.user, is_approved=True
        )
        Artifact.objects.create(
            project=self.project, stage='TESTING', version=1,
            content='{"generated_test_cases": [{"id": "TC-01", "scenario": "Test", "expected_result": "OK", "priority": "High", "status": "Not Executed"}]}',
            created_by=self.user, is_approved=True
        )

    def _valid_dep_json(self, deps_status="Ready"):
        import json
        return json.dumps({
            "deployment_recommendation": {
                "hosting_platform": "Render (Web Service)",
                "database_recommendation": "Render PostgreSQL",
                "config_requirements": ["Python 3.11+", "gunicorn", "HTTPS"],
                "explanation": "Simple PaaS host well-suited for Django web applications."
            },
            "deployment_readiness": [
                {"check": "Dependencies", "status": deps_status, "explanation": "Dependencies check."},
                {"check": "Environment Variables", "status": "Needs Review", "explanation": "Set SECRET_KEY and DATABASE_URL."},
                {"check": "Security", "status": "Missing", "explanation": "DEBUG=False not verified."},
                {"check": "Database", "status": "Ready", "explanation": "PostgreSQL supported via ORM."},
                {"check": "Static Files", "status": "Needs Review", "explanation": "Run collectstatic."}
            ],
            "deployment_instructions": {
                "steps": [
                    "1. Prepare production settings (DEBUG=False).",
                    "2. Configure environment variables in Render dashboard.",
                    "3. Provision PostgreSQL database.",
                    "4. Install dependencies.",
                    "5. Configure static files.",
                    "6. Deploy manually from Git branch.",
                    "7. Verify application works in browser."
                ],
                "verification_checklist": [
                    "Confirm HTTPS URL opens cleanly.",
                    "Check core pages render with CSS assets."
                ]
            }
        })

    @patch('ai_services.agents.groq_service.generate')
    @patch('ai_services.agents.jev_service.validate_artifact')
    def test_deployment_agent_evidence_guard_and_jev_validation(self, mock_validate, mock_generate):
        mock_generate.return_value = self._valid_dep_json(deps_status="Ready")
        mock_validate.return_value = {'valid': True, 'confidence': 0.92, 'issues': [], 'warnings': [], 'requires_human_review': True}

        dep_art = hitl_service.generate_initial_artifact(self.project, 'DEPLOYMENT', self.user)

        # Verify context includes approved v1 & excludes unapproved v2
        ctx = mock_generate.call_args[1]['context']
        self.assertIn("Approved Requirements v1", ctx)
        self.assertNotIn("UNAPPROVED DRAFT REQ DO NOT INCLUDE", ctx)
        self.assertIn("app/views.py", ctx)
        self.assertIn("TC-01", ctx)

        # Verify dependency evidence check downgraded false 'Ready' to 'Missing' since no requirements.txt exists
        import json
        saved = json.loads(dep_art.content)
        dep_chk = next(c for c in saved['deployment_readiness'] if c['check'] == 'Dependencies')
        self.assertEqual(dep_chk['status'], 'Missing')
        self.assertEqual(len(saved['deployment_readiness']), 5)

        # Verify Jev rules validated all 3 sections and readiness checks
        rules = mock_validate.call_args[1]['rules']
        self.assertTrue(any("three sections" in r.lower() for r in rules))
        self.assertTrue(any("five deployment readiness checks" in r.lower() for r in rules))

    @patch('ai_services.agents.groq_service.generate')
    def test_malformed_deployment_json_fails_gracefully(self, mock_generate):
        mock_generate.return_value = "{broken json without closing"
        with self.assertRaises(HITLServiceError) as cm:
            hitl_service.generate_initial_artifact(self.project, 'DEPLOYMENT', self.user)
        self.assertIn("Malformed JSON", str(cm.exception))
        self.assertEqual(Artifact.objects.filter(project=self.project, stage='DEPLOYMENT').count(), 0)

    def test_deployment_ui_renders_three_sections_and_hitl_completion(self):
        art_v1 = Artifact.objects.create(
            project=self.project, stage='DEPLOYMENT', version=1,
            content=self._valid_dep_json(deps_status="Missing"),
            created_by=self.user, is_approved=False,
            validation_meta={'valid': True, 'confidence': 0.91, 'issues': [], 'warnings': []}
        )

        self.client.force_login(self.user)
        res = self.client.get(reverse('stage_detail', kwargs={'project_id': self.project.pk, 'stage': 'DEPLOYMENT'}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Deployment Recommendation")
        self.assertContains(res, "Deployment Readiness")
        self.assertContains(res, "Deployment Instructions")
        self.assertContains(res, "Render (Web Service)")
        self.assertContains(res, "Render PostgreSQL")
        self.assertContains(res, "Dependencies")
        self.assertContains(res, "Static Files")
        self.assertContains(res, "Post-Deployment Verification Checklist")

        # Edit creates v2, Approve marks project COMPLETED
        v2 = hitl_service.edit_artifact(art_v1, self.user, self._valid_dep_json(deps_status="Needs Review"))
        self.assertEqual(v2.version, 2)
        hitl_service.approve_artifact(v2, self.user, "Ready for manual release.")

        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, 'COMPLETED')
        self.assertEqual(self.project.status, 'COMPLETED')

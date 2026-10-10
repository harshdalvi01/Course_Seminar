import logging
from typing import Dict, Any, Optional
from .groq_service import groq_service
from .jev_service import jev_service
from workflow.models import Artifact
from projects.models import Project

logger = logging.getLogger(__name__)

class BaseAgent:
    """
    Abstract base class for all SDLC specialized agents.
    Provides the standard workflow: generate (via Groq), validate (via Jev), and return_result.
    """
    stage_name = None
    
    def __init__(self):
        self.groq = groq_service
        self.jev = jev_service
        
    def _get_approved_artifact_content(self, project: Project, stage: str) -> Optional[str]:
        artifact = Artifact.objects.filter(
            project=project, 
            stage=stage, 
            is_approved=True
        ).order_by('-version').first()
        
        return artifact.content if artifact else None
        
    def build_context(self, project: Project) -> str:
        raise NotImplementedError
        
    def get_system_prompt(self) -> str:
        return f"You are the {self.__class__.__name__}. Generate the required output based on the context."
        
    def generate(self, project: Project, feedback: Optional[str] = None) -> str:
        """Generates the artifact content using Groq."""
        context = self.build_context(project)
        system_prompt = self.get_system_prompt()
        
        user_prompt = f"Please generate the {self.stage_name} artifact in pure Markdown format."
        if feedback:
            user_prompt += f"\n\nIMPORTANT - Human feedback on the previous version that you MUST incorporate:\n{feedback}"
        
        return self.groq.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            context=context
        )
        
    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        """Validates the generated output using Jev's decision support."""
        return self.jev.validate_artifact(
            content=output,
            stage=self.stage_name,
            rules=[f"Ensure valid {self.stage_name}"]
        )
        
    def return_result(self, content: str, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "stage": self.stage_name,
            "content": content,
            "validation": validation_result,
            "status": "success" if validation_result.get("valid") else "needs_review"
        }
        
    def execute(self, project: Project, feedback: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"Executing {self.__class__.__name__} for Project {project.id}")
        content = self.generate(project, feedback)
        validation = self.validate(content, project)
        return self.return_result(content, validation)


class RequirementAgent(BaseAgent):
    stage_name = 'REQUIREMENTS'
    
    def build_context(self, project: Project) -> str:
        return f"Project Idea:\n{project.description}"
        
    def get_system_prompt(self) -> str:
        return (
            "You are the expert Software Requirement Agent.\n"
            "Based on the provided project idea, generate a comprehensive software requirement specification.\n"
            "Your output MUST include exactly the following sections in Markdown:\n\n"
            "1. Project overview\n"
            "2. Functional requirements\n"
            "3. Non-functional requirements\n"
            "4. User roles\n"
            "5. Core features\n"
            "6. Constraints\n"
            "7. Acceptance criteria\n"
            "8. Assumptions\n"
            "9. Open questions\n\n"
            "Be highly structured, detailed, and professional."
        )
        
    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        rules = [
            "Evaluate completeness against the original project idea.",
            "Check for consistency across functional and non-functional requirements.",
            "Identify any ambiguity in the acceptance criteria or constraints.",
            "Identify any missing important information typical for software specs.",
            "Flag whether human review is required."
        ]
        return self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)


class DesignAgent(BaseAgent):
    stage_name = 'DESIGN'
    
    def build_context(self, project: Project) -> str:
        req = self._get_approved_artifact_content(project, 'REQUIREMENTS')
        if not req:
            raise ValueError("An approved REQUIREMENTS artifact must exist before generating DESIGN.")
        return f"Project Idea:\n{project.description}\n\nApproved Requirements:\n{req}"

    def get_system_prompt(self) -> str:
        return (
            "You are the expert Software Design Architect.\n"
            "Based on the project idea and approved requirements, generate a comprehensive software design document.\n"
            "Your output MUST include exactly the following sections in Markdown:\n\n"
            "1. System architecture\n"
            "2. Components/modules\n"
            "3. Database design\n"
            "4. API design\n"
            "5. Data flow\n"
            "6. Security considerations\n"
            "7. Important design decisions\n"
            "8. Assumptions\n\n"
            "Be highly structured, detailed, and professional."
        )
        
    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        rules = [
            "Evaluate consistency with the approved requirements.",
            "Identify any missing essential components or modules.",
            "Identify any potential architectural issues or bottlenecks.",
            "Identify any security concerns in the proposed design.",
            "Flag whether human review is required."
        ]
        return self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)

class CodingAgent(BaseAgent):
    stage_name = 'CODE'
    
    def build_context(self, project: Project) -> str:
        req = self._get_approved_artifact_content(project, 'REQUIREMENTS')
        design = self._get_approved_artifact_content(project, 'DESIGN')
        
        if not req or not design:
            raise ValueError("Both approved REQUIREMENTS and DESIGN artifacts must exist before generating CODE.")
            
        return (
            f"Project Idea:\n{project.description}\n\n"
            f"Approved Requirements:\n{req}\n\n"
            f"Approved Design:\n{design}"
        )

    def get_system_prompt(self) -> str:
        return (
            "You are the expert Lead Software Engineer.\n"
            "Based on the project idea, requirements, and architecture design, write the full codebase for the application.\n"
            "CRITICAL INSTRUCTION:\n"
            "You MUST output the result as a valid JSON block containing an array of file objects. "
            "Do not include any conversational text outside the JSON block. Format exactly like this:\n\n"
            "```json\n"
            "[\n"
            "  {\n"
            "    \"path\": \"app/models.py\",\n"
            "    \"purpose\": \"Defines the database models\",\n"
            "    \"content\": \"class User(models.Model):\\n    pass\"\n"
            "  }\n"
            "]\n"
            "```\n\n"
            "Ensure you include all necessary files (models, views, urls, HTML templates, etc.)."
        )
        
    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        rules = [
            "Evaluate requirement coverage (do the files cover the features?).",
            "Check design consistency against the approved architecture.",
            "Identify any obvious structural or logic issues in the code.",
            "Identify potential security concerns (e.g., SQL injection, XSS, hardcoded secrets).",
            "Identify any missing essential components or files.",
            "Flag whether human review is required."
        ]
        return self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)

class TestingAgent(BaseAgent):
    stage_name = 'TESTING'
    
    def build_context(self, project: Project) -> str:
        req = self._get_approved_artifact_content(project, 'REQUIREMENTS')
        design = self._get_approved_artifact_content(project, 'DESIGN')
        code = self._get_approved_artifact_content(project, 'CODE')
        
        if not req or not design or not code:
            raise ValueError("Approved REQUIREMENTS, DESIGN, and CODE artifacts must exist before generating TESTING.")
            
        return (
            f"Approved Requirements:\n{req}\n\n"
            f"Approved Design:\n{design}\n\n"
            f"Approved Code:\n{code}"
        )

    def get_system_prompt(self) -> str:
        return (
            "You are the expert Software QA and Testing Automation Engineer.\n"
            "Based on the requirements, design, and code provided, perform a rigorous static analysis "
            "and generate a comprehensive testing plan and report.\n"
            "Your output MUST be in Markdown and clearly separated into the following sections to match the UI spec:\n\n"
            "# Test Strategy\n"
            "1. Test strategy\n\n"
            "# Test Cases\n"
            "2. Unit test cases\n"
            "3. Integration test cases\n"
            "4. Functional test cases\n"
            "5. Edge cases\n\n"
            "# Coverage\n"
            "6. Requirements-to-test mapping\n\n"
            "# Potential Issues\n"
            "7. Static/review-based analysis\n"
            "8. Potential bugs\n\n"
            "# Security\n"
            "9. Security concerns\n\n"
            "# Recommendations\n"
            "10. Recommendations\n\n"
            "CRITICAL: Do NOT attempt to run scripts or execute code. Rely strictly on static analysis."
        )
        
    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        rules = [
            "Evaluate requirement coverage (do the tests cover all features?).",
            "Identify missing test areas or edge cases.",
            "Verify consistency with approved requirements.",
            "Assess the severity of any identified issues or potential bugs.",
            "Flag whether human review is required."
        ]
        return self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)

class DeploymentAgent(BaseAgent):
    stage_name = 'DEPLOYMENT'
    def build_context(self, project: Project) -> str:
        req = self._get_approved_artifact_content(project, 'REQUIREMENTS') or "[Missing]"
        design = self._get_approved_artifact_content(project, 'DESIGN') or "[Missing]"
        code = self._get_approved_artifact_content(project, 'CODE') or "[Missing]"
        tests = self._get_approved_artifact_content(project, 'TESTING') or "[Missing]"
        return f"Requirements:\n{req}\n\nDesign:\n{design}\n\nCode:\n{code}\n\nTests:\n{tests}"

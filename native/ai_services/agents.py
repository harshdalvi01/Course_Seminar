import json
import logging
from typing import Dict, Any, Optional
from .groq_service import groq_service
from .jev_service import jev_service
from workflow.models import Artifact
from projects.models import Project

logger = logging.getLogger(__name__)

def condense_text(text: Optional[str], max_chars: int = 3000) -> str:
    """
    Safely limits text size while keeping beginning and ending context.
    If the text is already concise, it is returned untouched.
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    omitted = len(text) - max_chars
    return (
        f"{text[:half]}\n\n"
        f"... [Summary: {omitted} characters condensed for token economy] ...\n\n"
        f"{text[-half:]}"
    )

def condense_code_artifact(code_str: Optional[str], max_file_chars: int = 600) -> str:
    """
    Parses a code artifact (JSON array of files or Markdown) and generates
    a concise architectural summary and manifest for downstream agents.
    If the code is already concise (or a short test string), it is preserved.
    """
    if not code_str:
        return ""
        
    if len(code_str) <= 1500:
        return code_str

    clean_str = code_str.strip()
    if clean_str.startswith("```json"):
        clean_str = clean_str[7:]
    elif clean_str.startswith("```"):
        clean_str = clean_str[3:]
    if clean_str.endswith("```"):
        clean_str = clean_str[:-3]
    clean_str = clean_str.strip()

    parsed_files = None
    try:
        data = json.loads(clean_str)
        if isinstance(data, list):
            parsed_files = data
    except Exception:
        pass

    if parsed_files:
        manifest_lines = [
            "### Codebase Architectural Manifest & Key Excerpts:",
            f"Total files: {len(parsed_files)}"
        ]
        for f in parsed_files:
            path = f.get('path', 'unknown')
            purpose = f.get('purpose', 'N/A')
            content = f.get('content', '')
            
            # Key configuration / setup files retain more content
            is_config = any(path.endswith(cfg) for cfg in ['package.json', 'requirements.txt', 'Dockerfile', 'docker-compose.yml', 'tsconfig.json'])
            char_limit = max_file_chars * 2 if is_config else max_file_chars
            
            if len(content) > char_limit:
                truncated_content = content[:char_limit] + f"\n... [Truncated {len(content) - char_limit} chars for token economy]"
            else:
                truncated_content = content
                
            manifest_lines.append(f"\n- **File `{path}`** ({purpose}):\n```\n{truncated_content}\n```")
            
        return "\n".join(manifest_lines)

    # Fallback for non-JSON code artifacts (e.g. plain text or markdown)
    return condense_text(code_str, max_chars=3500)


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
        return f"Project Idea:\n{project.description}\n\nApproved Requirements:\n{condense_text(req, max_chars=3500)}"

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
            f"Approved Requirements:\n{condense_text(req, max_chars=3000)}\n\n"
            f"Approved Design:\n{condense_text(design, max_chars=3000)}"
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
            f"Approved Requirements:\n{condense_text(req, max_chars=2500)}\n\n"
            f"Approved Design:\n{condense_text(design, max_chars=2500)}\n\n"
            f"Approved Code:\n{condense_code_artifact(code, max_file_chars=500)}"
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
        req = self._get_approved_artifact_content(project, 'REQUIREMENTS')
        design = self._get_approved_artifact_content(project, 'DESIGN')
        code = self._get_approved_artifact_content(project, 'CODE')
        testing = self._get_approved_artifact_content(project, 'TESTING')
        
        if not req or not design or not code or not testing:
            raise ValueError("Approved REQUIREMENTS, DESIGN, CODE, and TESTING artifacts must exist before generating DEPLOYMENT.")
            
        return (
            f"Project Idea:\n{project.description}\n\n"
            f"Approved Requirements:\n{condense_text(req, max_chars=2000)}\n\n"
            f"Approved Design:\n{condense_text(design, max_chars=2000)}\n\n"
            f"Approved Code:\n{condense_code_artifact(code, max_file_chars=400)}\n\n"
            f"Approved Testing Strategy & Report:\n{condense_text(testing, max_chars=2000)}"
        )

    def get_system_prompt(self) -> str:
        return (
            "You are the expert DevOps, Cloud Architect, and Release Engineer.\n"
            "Based on the approved requirements, system design, source code, and testing reports, "
            "generate a comprehensive deployment plan and readiness assessment.\n\n"
            "CRITICAL SAFETY INSTRUCTION:\n"
            "Do NOT attempt to execute deployment commands, install packages, or provision infrastructure. "
            "This agent creates an architectural release specification and static deployment readiness report.\n\n"
            "Your output MUST be in structured Markdown format containing the following 10 numbered sections:\n\n"
            "# 1. Deployment Strategy\n"
            "Define the chosen strategy (e.g., Blue/Green, Canary, Rolling, or Containerized Static Host) and rationale.\n\n"
            "# 2. Environment Requirements\n"
            "Specify operating system, runtime versions (e.g., Node.js / Python), CPU/RAM recommendations, and network requirements.\n\n"
            "# 3. Required Services\n"
            "Detail external services, web servers (e.g., Nginx, Caddy), background workers, CDN, or cache layers.\n\n"
            "# 4. Configuration Requirements\n"
            "List environment variables, configuration files, secrets management, and port bindings.\n\n"
            "# 5. Database Considerations\n"
            "Outline data persistence, migration procedures, indexing, backup routines, and storage requirements.\n\n"
            "# 6. Security Checklist\n"
            "Provide production hardening steps: SSL/TLS enforcement, headers, CORS policy, secret isolation, and least-privilege permissions.\n\n"
            "# 7. CI/CD Recommendations\n"
            "Recommend automated build, lint, test, and release verification stages for continuous integration.\n\n"
            "# 8. Monitoring Considerations\n"
            "Detail health check endpoints, logging aggregation, uptime monitoring, error tracking, and alerting thresholds.\n\n"
            "# 9. Rollback Strategy\n"
            "Define concrete steps to rapidly revert to the previous stable release in case of critical deployment failure.\n\n"
            "# 10. Deployment Readiness Assessment\n"
            "Provide an objective Go / No-Go readiness summary, risk rating, and prerequisite checklist for human authorization."
        )

    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        rules = [
            "Identify missing deployment requirements, environment configurations, or unaccounted dependencies.",
            "Identify critical security concerns (e.g., insecure defaults, exposed secrets, unencrypted communications).",
            "Verify consistency with the project's approved design, code, and test artifacts.",
            "Evaluate overall deployment readiness (Go / No-Go clarity and risk assessment).",
            "Flag whether human review is required."
        ]
        return self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)


import re
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



DIAGRAM_CONFIGS = {
    'system_architecture': {
        'title': 'System Architecture Diagram',
        'category': 'Essential',
        'directive': 'flowchart TD',
        'syntax_prefix': ('flowchart', 'graph'),
        'description_template': 'High-level component topology illustrating frontend client, backend services, database persistence, and external integrations.',
        'is_essential': True,
    },
    'use_case': {
        'title': 'Use Case Diagram',
        'category': 'Essential',
        'directive': 'flowchart LR',
        'syntax_prefix': ('flowchart', 'graph'),
        'description_template': 'Visual actor-to-functionality representation mapping primary human/system actors to application capabilities.',
        'is_essential': True,
    },
    'erd': {
        'title': 'Entity Relationship Diagram (ERD)',
        'category': 'Essential',
        'directive': 'erDiagram',
        'syntax_prefix': ('erDiagram',),
        'description_template': 'Relational entity schemas, attributes, primary/foreign key relationships, and cardinalities.',
        'is_essential': True,
    },
    'class_diagram': {
        'title': 'Class Diagram',
        'category': 'Recommended',
        'directive': 'classDiagram',
        'syntax_prefix': ('classDiagram',),
        'description_template': 'Key domain classes, member attributes, methods, inheritance, and associations.',
        'is_essential': False,
    },
    'sequence_diagram': {
        'title': 'Sequence Diagram',
        'category': 'Recommended',
        'directive': 'sequenceDiagram',
        'syntax_prefix': ('sequenceDiagram',),
        'description_template': 'Chronological execution flow and request/response lifecycles across actors and services.',
        'is_essential': False,
    },
}

def replace_diagram_in_markdown(content: str, diagram_type: str, new_diagram_text: str) -> str:
    """
    Safely replaces or inserts a single diagram definition under the '# System Design Diagrams'
    section in the design markdown document, preserving all other sections and diagrams.
    """
    patterns = {
        'system_architecture': r'(###\s*(?:\d+\.\s*)?System Architecture[^\n]*\n)(.*?)(?=(?:\n###|\n##|\n#|\Z))',
        'use_case': r'(###\s*(?:\d+\.\s*)?Use Case[^\n]*\n)(.*?)(?=(?:\n###|\n##|\n#|\Z))',
        'erd': r'(###\s*(?:\d+\.\s*)?(?:Entity Relationship|ERD)[^\n]*\n)(.*?)(?=(?:\n###|\n##|\n#|\Z))',
        'class_diagram': r'(###\s*(?:\d+\.\s*)?Class Diagram[^\n]*\n)(.*?)(?=(?:\n###|\n##|\n#|\Z))',
        'sequence_diagram': r'(###\s*(?:\d+\.\s*)?Sequence Diagram[^\n]*\n)(.*?)(?=(?:\n###|\n##|\n#|\Z))',
    }
    pat = patterns.get(diagram_type)
    if pat and re.search(pat, content, re.DOTALL | re.IGNORECASE):
        cleaned_new = new_diagram_text.strip()
        m = re.match(r'^###[^\n]*\n(.*)$', cleaned_new, re.DOTALL)
        if m:
            replacement_body = m.group(1).strip()
            return re.sub(pat, lambda match: match.group(1) + replacement_body + '\n\n', content, count=1, flags=re.DOTALL | re.IGNORECASE)
        else:
            return re.sub(pat, lambda match: match.group(1) + cleaned_new + '\n\n', content, count=1, flags=re.DOTALL | re.IGNORECASE)
    else:
        if '# System Design Diagrams' not in content:
            return content.rstrip() + '\n\n# System Design Diagrams\n\n' + new_diagram_text.strip() + '\n'
        else:
            return content.rstrip() + '\n\n' + new_diagram_text.strip() + '\n'


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
            "Based on the project idea and approved requirements, generate a comprehensive software design document and diagram specification.\n"
            "Your output MUST include exactly the following technical sections in structured Markdown:\n\n"
            "## 1. System Architecture\n"
            "## 2. Components/Modules\n"
            "## 3. Database Design\n"
            "## 4. API Design\n"
            "## 5. Data Flow\n"
            "## 6. Security Considerations\n"
            "## 7. Important Design Decisions\n"
            "## 8. Assumptions\n\n"
            "# System Design Diagrams\n\n"
            "Immediately following the written documentation, you MUST include a dedicated section titled exactly `# System Design Diagrams`.\n"
            "In this section, you MUST generate visual Mermaid diagrams based strictly on the approved requirements. "
            "You MUST generate the three Essential diagrams, and generate the two Recommended diagrams ONLY if sufficient information exists in the requirements.\n\n"
            "Generate ONLY these five diagram types. Do NOT generate activity diagrams, deployment diagrams, component diagrams, or state diagrams.\n\n"
            "### 1. System Architecture Diagram (Essential)\n"
            "- Mermaid syntax: ```mermaid\\nflowchart TD ...```\n"
            "- Shows overall application topology: frontend, backend, database, external APIs, and connection protocols.\n"
            "- Format:\n"
            "**Type:** System Architecture Diagram (Essential)\n"
            "**Status:** Generated\n"
            "**Description:** [Short explanation of client, server, database, and integrations]\n"
            "```mermaid\n"
            "flowchart TD\n"
            "...\n"
            "```\n"
            "**Key Observations:** [Key design observations]\n\n"
            "### 2. Use Case Diagram (Essential)\n"
            "- Mermaid syntax: ```mermaid\\nflowchart LR ...```\n"
            "- Shows visual actor-to-functionality representation mapping user personas to major capabilities.\n"
            "- Format:\n"
            "**Type:** Use Case Diagram (Essential)\n"
            "**Status:** Generated\n"
            "**Description:** [Short explanation of actors and major functionalities]\n"
            "```mermaid\n"
            "flowchart LR\n"
            "...\n"
            "```\n"
            "**Key Observations:** [Key design observations]\n\n"
            "### 3. Entity Relationship Diagram (Essential)\n"
            "- Mermaid syntax: ```mermaid\\nerDiagram ...```\n"
            "- Shows database entities, attributes, PK/FK flags, and relationships with cardinalities.\n"
            "- Format:\n"
            "**Type:** Entity Relationship Diagram (Essential)\n"
            "**Status:** Generated\n"
            "**Description:** [Short explanation of database entities and relationships]\n"
            "```mermaid\n"
            "erDiagram\n"
            "...\n"
            "```\n"
            "**Key Observations:** [Key design observations]\n\n"
            "### 4. Class Diagram (Recommended)\n"
            "- If requirements support classes/domain models:\n"
            "**Type:** Class Diagram (Recommended)\n"
            "**Status:** Generated\n"
            "**Description:** [Short explanation of major classes, attributes, methods, relationships]\n"
            "```mermaid\n"
            "classDiagram\n"
            "...\n"
            "```\n"
            "**Key Observations:** [Key design observations]\n\n"
            "- If requirements do NOT contain sufficient object-oriented class specifications, do NOT invent them. Set:\n"
            "**Type:** Class Diagram (Recommended)\n"
            "**Status:** Not Generated\n"
            "**Description:** Not generated: The approved requirements do not specify an object-oriented domain model or distinct class hierarchies.\n"
            "**Key Observations:** System relies on procedural/API endpoints rather than class-based OOP architectures.\n\n"
            "### 5. Sequence Diagram (Recommended)\n"
            "- If requirements support multi-component sequence workflows:\n"
            "**Type:** Sequence Diagram (Recommended)\n"
            "**Status:** Generated\n"
            "**Description:** [Short explanation of component request/response sequence]\n"
            "```mermaid\n"
            "sequenceDiagram\n"
            "...\n"
            "```\n"
            "**Key Observations:** [Key design observations]\n\n"
            "- If requirements lack multi-step sequence workflows, do NOT invent them. Set:\n"
            "**Type:** Sequence Diagram (Recommended)\n"
            "**Status:** Not Generated\n"
            "**Description:** Not generated: The approved requirements do not specify multi-step asynchronous or multi-component transaction workflows.\n"
            "**Key Observations:** Direct synchronous interactions without complex sequence lifecycles.\n\n"
            "CRITICAL MERMAID SYNTAX RULES:\n"
            "1. In flowcharts (flowchart TD, flowchart LR):\n"
            "   - When any node label contains parentheses `( )`, brackets `[ ]`, braces `{ }`, slashes, commas, or special characters, ALWAYS enclose the label in double quotes inside the shape delimiter. Example: `NodeId[\"Static Web Server (e.g., GitHub Pages)\"]`, `UC2[\"Clear Entry (C)\"]`, `Actor([\"User (Admin)\"])`.\n"
            "   - NEVER write unquoted parentheses inside square brackets like `NodeId[Text (with parens)]` because Mermaid treats parentheses as shape delimiters and throws a syntax parse error.\n"
            "   - Node IDs must be clean alphanumeric words without spaces or symbols.\n\n"
            "Be highly structured, detailed, professional, and strictly output valid Mermaid syntax."
        )

    def regenerate_single_diagram(self, project: Project, current_content: str, diagram_type: str, feedback: Optional[str] = None) -> str:
        """
        Regenerates an individual diagram within an existing design artifact,
        preserving all other written sections and diagrams.
        """
        config = DIAGRAM_CONFIGS.get(diagram_type)
        if not config:
            raise ValueError(f"Unknown diagram type: {diagram_type}")

        context = self.build_context(project)
        system_prompt = (
            f"You are the expert Software Design Architect.\n"
            f"You are tasked with regenerating ONLY the following diagram based strictly on the approved requirements:\n"
            f"Diagram: {config['title']} ({config['category']})\n"
            f"Required Mermaid syntax format: {config['directive']}\n\n"
            f"Requirements to observe strictly:\n"
            f"1. Generate ONLY the single requested diagram.\n"
            f"2. Use clean, valid Mermaid syntax ({config['directive']}). Always enclose node labels containing parentheses or special characters in double quotes: e.g. NodeId[\"Label (extra)\"].\n"
            f"3. Base all components strictly on the approved requirements. Do not invent unauthorized entities, APIs, or actors.\n"
            f"4. If this is a Recommended diagram and requirements lack sufficient information, set Status to 'Not Generated' and provide a clear explanation in Description.\n"
            f"5. Output format must match exactly:\n\n"
            f"### {config['title']} ({config['category']})\n"
            f"**Type:** {config['title']} ({config['category']})\n"
            f"**Status:** Generated\n"
            f"**Description:** [Short explanation]\n"
            f"```mermaid\n"
            f"{config['directive']}\n"
            f"...\n"
            f"```\n"
            f"**Key Observations:** [Key design observations]"
        )
        user_prompt = f"Please regenerate the {config['title']} for this project."
        if feedback:
            user_prompt += f"\n\nHuman Reviewer Directives / Feedback for this diagram:\n{feedback}"

        generated_diagram_text = self.groq.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            context=context
        )

        return replace_diagram_in_markdown(current_content, diagram_type, generated_diagram_text)

    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        rules = [
            "Evaluate consistency with the approved requirements.",
            "Verify presence and completeness of the three essential diagrams (System Architecture, Use Case, ERD).",
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


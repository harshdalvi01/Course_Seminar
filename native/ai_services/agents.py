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
            "## 4. Data Flow\n\n"
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
            f"Project Title: {project.name}\n"
            f"Project Idea/Description: {project.description}\n\n"
            f"Approved Requirements:\n{condense_text(req, max_chars=3500)}\n\n"
            f"Approved Design:\n{condense_text(design, max_chars=2500)}\n\n"
            f"Approved Code Artifacts & Source Files:\n{condense_code_artifact(code, max_file_chars=1200)}"
        )

    def get_system_prompt(self) -> str:
        return (
            "You are an expert QA Engineer and Static Code Review Architect.\n"
            "Evaluate the approved Coding Agent source files strictly against the approved Requirements and Design.\n"
            "Generate a concise, structured set of Generated Test Cases in valid JSON format.\n\n"
            "CRITICAL SAFETY AND SCOPE RULES:\n"
            "- Do NOT attempt to run code, execute test cases, install dependencies, or claim any test passed.\n"
            "- EVERY test case MUST have status \"Not Executed\".\n"
            "- Do NOT invent features or requirements not present in the approved artifacts.\n\n"
            "REQUIRED OUTPUT FORMAT:\n"
            "Return ONLY a single valid JSON object (wrapped in ```json ... ``` or raw JSON) with NO extra conversational text outside it:\n"
            "```json\n"
            "{\n"
            "  \"generated_test_cases\": [\n"
            "    {\n"
            "      \"id\": \"TC-01\",\n"
            "      \"scenario\": \"Concise test case description\",\n"
            "      \"scenario_type\": \"Positive\",\n"
            "      \"requirement_ref\": \"FR-01\",\n"
            "      \"expected_result\": \"Expected observable outcome\",\n"
            "      \"priority\": \"High\",\n"
            "      \"status\": \"Not Executed\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            "GUIDELINES:\n"
            "- Generate approximately 8-12 concise, relevant test cases depending on project complexity.\n"
            "- Include a balanced mix of Positive and Negative test scenarios mapped directly to approved requirements.\n"
            "- Keep scenarios and expected results easy to read and strictly non-executed."
        )

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Safely extracts and parses JSON from Groq output."""
        if not raw_text or not isinstance(raw_text, str):
            raise ValueError("Empty response received from Groq Testing Agent.")

        cleaned = raw_text.strip()
        if "```" in cleaned:
            m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*(?:```|\Z)', cleaned)
            if m:
                cleaned = m.group(1).strip()

        if not cleaned.startswith('{'):
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end + 1]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON Testing Report returned by Groq: {str(e)}")

        if not isinstance(parsed, dict):
            raise ValueError("Testing Report root payload must be a JSON object.")

        return parsed

    def _validate_and_normalize_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates test cases schema, enforces 'Not Executed' safety constraint, and checks math consistency."""
        if 'generated_test_cases' not in data:
            raise ValueError("Malformed Testing Report schema: missing required section 'generated_test_cases'.")

        if not isinstance(data['generated_test_cases'], list) or len(data['generated_test_cases']) == 0:
            raise ValueError("Malformed Testing Report: 'generated_test_cases' must be a non-empty list.")

        if 'testing_summary' not in data or not isinstance(data['testing_summary'], dict):
            data['testing_summary'] = {}
        if 'potential_issues' not in data or not isinstance(data['potential_issues'], list):
            data['potential_issues'] = []
        if 'recommendations' not in data or not isinstance(data['recommendations'], list):
            data['recommendations'] = []

        # Normalize & validate test cases
        norm_cases = []
        valid_priorities = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}
        for idx, tc in enumerate(data['generated_test_cases'], 1):
            if not isinstance(tc, dict):
                raise ValueError(f"Test case #{idx} must be a JSON object.")
            scenario = str(tc.get('scenario', '')).strip()
            expected = str(tc.get('expected_result', '')).strip()
            if not scenario or not expected:
                raise ValueError(f"Test case #{idx} is missing required 'scenario' or 'expected_result'.")
            prio_raw = str(tc.get('priority', 'Medium')).strip().lower()
            priority = valid_priorities.get(prio_raw, 'Medium')
            stype_raw = str(tc.get('scenario_type', 'Positive')).strip().lower()
            scenario_type = 'Negative' if 'neg' in stype_raw else 'Positive'
            norm_cases.append({
                'id': str(tc.get('id') or f"TC-{idx:02d}").strip(),
                'scenario': scenario,
                'scenario_type': scenario_type,
                'requirement_ref': str(tc.get('requirement_ref') or 'General').strip(),
                'expected_result': expected,
                'priority': priority,
                'status': 'Not Executed',  # Strictly enforced safety rule: never executed / never claimed passed
            })

        # Normalize potential issues
        norm_issues = []
        valid_severities = {'critical': 'Critical', 'high': 'High', 'medium': 'Medium', 'low': 'Low'}
        for idx, iss in enumerate(data['potential_issues'], 1):
            if not isinstance(iss, dict):
                continue
            desc = str(iss.get('description', '')).strip()
            expl = str(iss.get('explanation', '')).strip()
            if not desc:
                continue
            sev_raw = str(iss.get('severity', 'Medium')).strip().lower()
            severity = valid_severities.get(sev_raw, 'Medium')
            norm_issues.append({
                'id': str(iss.get('id') or f"ISS-{idx:02d}").strip(),
                'description': desc,
                'severity': severity,
                'affected_component': str(iss.get('affected_component') or 'Unspecified Component').strip(),
                'explanation': expl or "Identified via static code review; requires manual verification.",
                'analysis_type': 'AI Static Analysis (Unverified at Runtime)',
            })

        # Normalize recommendations
        norm_recs = []
        for idx, rec in enumerate(data['recommendations'], 1):
            if isinstance(rec, str) and rec.strip():
                norm_recs.append({
                    'title': f"Recommendation #{idx}",
                    'action': rec.strip(),
                    'related_ref': '',
                })
            elif isinstance(rec, dict):
                action = str(rec.get('action') or rec.get('description') or '').strip()
                if action:
                    norm_recs.append({
                        'title': str(rec.get('title') or f"Recommendation #{idx}").strip(),
                        'action': action,
                        'related_ref': str(rec.get('related_ref') or '').strip(),
                    })

        # Recompute & enforce internally consistent Testing Summary metrics
        raw_sum = data['testing_summary']
        covered_reqs = raw_sum.get('covered_requirements', [])
        if not isinstance(covered_reqs, list):
            covered_reqs = []
        covered_reqs = [str(r).strip() for r in covered_reqs if str(r).strip()]

        uncovered_reqs = raw_sum.get('uncovered_requirements', [])
        if not isinstance(uncovered_reqs, list):
            uncovered_reqs = []
        uncovered_reqs = [str(r).strip() for r in uncovered_reqs if str(r).strip()]

        # Deduplicate references if covered_requirements is empty
        if not covered_reqs:
            seen = []
            for tc in norm_cases:
                ref = tc['requirement_ref']
                if ref and ref.lower() != 'general' and ref not in seen:
                    seen.append(ref)
            covered_reqs = seen

        raw_total_reqs = raw_sum.get('total_requirements_count', 0)
        try:
            total_reqs_num = int(raw_total_reqs)
        except (ValueError, TypeError):
            total_reqs_num = 0

        derived_total_reqs = len(covered_reqs) + len(uncovered_reqs)
        total_reqs_count = max(total_reqs_num, derived_total_reqs)

        if total_reqs_count > 0:
            coverage_pct = round((len(covered_reqs) / total_reqs_count) * 100.0, 1)
            coverage_pct = min(100.0, max(0.0, coverage_pct))
        else:
            try:
                coverage_pct = round(min(100.0, max(0.0, float(raw_sum.get('requirement_coverage_percentage', 0.0)))), 1)
            except (ValueError, TypeError):
                coverage_pct = 0.0

        summary_note = str(raw_sum.get('summary_note') or '').strip()
        if not summary_note:
            if norm_issues:
                summary_note = (
                    f"Generated {len(norm_cases)} static test cases covering {len(covered_reqs)}/{total_reqs_count or '?'} "
                    f"tracked requirements. {len(norm_issues)} potential static issue(s) flagged for human review. "
                    "No code or tests were executed."
                )
            else:
                summary_note = (
                    f"Generated {len(norm_cases)} static test cases. No significant potential issues were identified in the reviewed artifacts. "
                    "No code or tests were executed."
                )

        normalized_summary = {
            'total_test_cases': len(norm_cases),
            'requirement_coverage_percentage': coverage_pct,
            'covered_requirements': covered_reqs,
            'uncovered_requirements': uncovered_reqs,
            'total_requirements_count': total_reqs_count,
            'potential_issues_count': len(norm_issues),
            'summary_note': summary_note,
        }

        return {
            'testing_summary': normalized_summary,
            'generated_test_cases': norm_cases,
            'potential_issues': norm_issues,
            'recommendations': norm_recs,
        }

    def generate(self, project: Project, feedback: Optional[str] = None) -> str:
        """Generates, parses, validates, and returns a canonical JSON Consolidated Testing Report."""
        context = self.build_context(project)
        system_prompt = self.get_system_prompt()

        user_prompt = (
            "Please generate the Consolidated Testing Report in valid JSON format following the exact 4-section schema. "
            "Ensure all test cases use status 'Not Executed' and ground any potential issues directly in the reviewed code."
        )
        if feedback:
            user_prompt += f"\n\nIMPORTANT - Human reviewer directives on the previous report that you MUST incorporate:\n{feedback}"

        raw_output = self.groq.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            context=context
        )

        parsed_json = self._extract_json(raw_output)
        normalized_report = self._validate_and_normalize_report(parsed_json)
        return json.dumps(normalized_report, indent=2)

    def _run_local_consistency_checks(self, output: str) -> Dict[str, Any]:
        """Verifies structural integrity, required fields, status rules, and coverage calculation consistency."""
        local_issues = []
        local_warnings = []
        try:
            data = self._extract_json(output)
        except ValueError as e:
            local_issues.append(f"Structural validation failed: {str(e)}")
            return {'valid': False, 'issues': local_issues, 'warnings': local_warnings}

        if 'generated_test_cases' not in data:
            local_issues.append("Missing required report section: 'generated_test_cases'.")

        cases = data.get('generated_test_cases', [])
        if isinstance(cases, list):
            for i, tc in enumerate(cases, 1):
                if not isinstance(tc, dict):
                    local_issues.append(f"Test case #{i} is not a structured object.")
                    continue
                if not tc.get('id') or not tc.get('scenario') or not tc.get('expected_result') or not tc.get('priority'):
                    local_issues.append(f"Test case {tc.get('id', i)} is missing required fields.")
                if tc.get('status') != 'Not Executed':
                    local_issues.append(f"Safety check: Test case {tc.get('id', i)} status must be 'Not Executed'.")
        else:
            local_issues.append("'generated_test_cases' must be a list.")

        summary = data.get('testing_summary', {})
        if isinstance(summary, dict) and isinstance(cases, list):
            if summary.get('total_test_cases') != len(cases):
                local_warnings.append(
                    f"Summary total_test_cases ({summary.get('total_test_cases')}) differs from actual count ({len(cases)})."
                )
            total_reqs = summary.get('total_requirements_count', 0)
            cov_reqs = summary.get('covered_requirements', [])
            if isinstance(total_reqs, int) and total_reqs > 0 and isinstance(cov_reqs, list):
                expected_pct = round((len(cov_reqs) / total_reqs) * 100.0, 1)
                reported_pct = float(summary.get('requirement_coverage_percentage', 0.0))
                if abs(expected_pct - reported_pct) > 1.5:
                    local_warnings.append(
                        f"Coverage calculation variance: {len(cov_reqs)}/{total_reqs} = {expected_pct}%, reported {reported_pct}%."
                    )

        issues_list = data.get('potential_issues', [])
        if isinstance(issues_list, list):
            if isinstance(summary, dict) and summary.get('potential_issues_count') != len(issues_list):
                local_warnings.append("Summary potential_issues_count differs from potential_issues length.")
            for iss in issues_list:
                if isinstance(iss, dict) and (not iss.get('description') or not iss.get('severity')):
                    local_warnings.append("An identified potential issue lacks a clear severity or description.")

        recs = data.get('recommendations', [])
        if isinstance(recs, list) and len(recs) == 0 and (len(issues_list) > 0 or len(summary.get('uncovered_requirements', [])) > 0):
            local_warnings.append("Recommendations section is empty despite identified issues or uncovered requirements.")

        return {
            'valid': len(local_issues) == 0,
            'issues': local_issues,
            'warnings': local_warnings,
        }

    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        local_check = self._run_local_consistency_checks(output)

        rules = [
            "Verify whether all four report sections (Testing Summary, Generated Test Cases, Potential Issues, Recommendations) are present.",
            "Verify whether generated test cases contain required fields (ID, scenario, expected result, priority, status='Not Executed').",
            "Verify whether test cases relate meaningfully to the approved requirements.",
            "Verify whether requirement coverage calculations in Testing Summary are internally consistent.",
            "Verify whether potential issues and recommendations have sufficient supporting context and are framed as unverified static findings."
        ]
        jev_res = self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)

        # Merge deterministic structural/consistency findings without discarding Jev output
        merged_issues = list(jev_res.get('issues') or []) + local_check['issues']
        merged_warnings = list(jev_res.get('warnings') or []) + local_check['warnings']

        jev_res['issues'] = merged_issues
        jev_res['warnings'] = merged_warnings
        jev_res['valid'] = bool(jev_res.get('valid', True)) and local_check['valid']
        jev_res['requires_human_review'] = True
        return jev_res

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
            f"Project Name: {project.name}\n"
            f"Project Idea/Description: {project.description}\n\n"
            f"Approved Requirements:\n{condense_text(req, max_chars=2500)}\n\n"
            f"Approved Design:\n{condense_text(design, max_chars=2500)}\n\n"
            f"Approved Code & Configuration Files:\n{condense_code_artifact(code, max_file_chars=1000)}\n\n"
            f"Approved Testing Report:\n{condense_text(testing, max_chars=2000)}"
        )

    def get_system_prompt(self) -> str:
        return (
            "You are a pragmatic Senior Release Engineer helping a developer manually deploy an academic software prototype.\n"
            "Analyze the approved Requirements, Design, Code files, and Testing Report to generate ONE lightweight, consolidated Deployment Report in valid JSON.\n\n"
            "STRICT SCOPE & SAFETY RESTRICTIONS:\n"
            "- Do NOT propose or generate Dockerfiles, Kubernetes manifests, Terraform, or CI/CD pipeline YAML.\n"
            "- Do NOT include automated deployment scripts or shell automation.\n"
            "- Do NOT request cloud credentials or include real secrets/API keys.\n"
            "- Deployment is performed MANUALLY by the human developer following your concise guide.\n"
            "- NEVER invent successful readiness checks when evidence is missing in the reviewed code. Mark absent items 'Missing' or 'Needs Review' (or 'Not Applicable' if truly unnecessary, e.g., Database for pure client-side apps).\n\n"
            "REQUIRED OUTPUT FORMAT:\n"
            "Return ONLY a single valid JSON object (wrapped in ```json ... ``` or raw JSON) with NO conversational text outside it, matching these exact 3 sections:\n"
            "```json\n"
            "{\n"
            "  \"deployment_recommendation\": {\n"
            "    \"hosting_platform\": \"Simple managed host suited to stack (e.g., Render, PythonAnywhere, GitHub Pages, Netlify, Railway)\",\n"
            "    \"database_recommendation\": \"Simple database setup (e.g., Render Managed PostgreSQL, SQLite, or Not Required for static frontend)\",\n"
            "    \"config_requirements\": [\"Python 3.11+ runtime\", \"WSGI server (gunicorn)\", \"HTTPS enforced\"],\n"
            "    \"explanation\": \"Short 1-2 sentence explanation tailored directly to the project's actual stack.\"\n"
            "  },\n"
            "  \"deployment_readiness\": [\n"
            "    {\n"
            "      \"check\": \"Dependencies\",\n"
            "      \"status\": \"Ready | Needs Review | Missing | Not Applicable\",\n"
            "      \"explanation\": \"Factual observation grounded in the reviewed code files.\"\n"
            "    },\n"
            "    {\n"
            "      \"check\": \"Environment Variables\",\n"
            "      \"status\": \"Ready | Needs Review | Missing | Not Applicable\",\n"
            "      \"explanation\": \"Are required env vars identified and documented?\"\n"
            "    },\n"
            "    {\n"
            "      \"check\": \"Security\",\n"
            "      \"status\": \"Ready | Needs Review | Missing | Not Applicable\",\n"
            "      \"explanation\": \"Are secrets outside source code and production DEBUG addressed?\"\n"
            "    },\n"
            "    {\n"
            "      \"check\": \"Database\",\n"
            "      \"status\": \"Ready | Needs Review | Missing | Not Applicable\",\n"
            "      \"explanation\": \"Is database configuration suitable for recommended deployment?\"\n"
            "    },\n"
            "    {\n"
            "      \"check\": \"Static Files\",\n"
            "      \"status\": \"Ready | Needs Review | Missing | Not Applicable\",\n"
            "      \"explanation\": \"Is static asset serving configured for production?\"\n"
            "    }\n"
            "  ],\n"
            "  \"deployment_instructions\": {\n"
            "    \"steps\": [\n"
            "      \"1. Prepare the production configuration (set DEBUG=False, configure allowed hosts).\",\n"
            "      \"2. Configure environment variables (SECRET_KEY, DATABASE_URL, API keys) in the hosting dashboard.\",\n"
            "      \"3. Set up the database (provision instance and run migrations if applicable).\",\n"
            "      \"4. Install dependencies using the project dependency file.\",\n"
            "      \"5. Configure static files (run collectstatic or specify public build directory).\",\n"
            "      \"6. Deploy the application manually by linking the repository or uploading build artifacts.\",\n"
            "      \"7. Verify that the application works using the checklist below.\"\n"
            "    ],\n"
            "    \"verification_checklist\": [\n"
            "      \"Open the live application URL over HTTPS.\",\n"
            "      \"Verify primary core features and asset loading work without errors.\"\n"
            "    ]\n"
            "  }\n"
            "}\n"
            "```\n\n"
            "Keep instructions strictly adapted to the actual tech stack, concise, clear, and academic-prototype friendly."
        )

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Safely extracts and parses JSON from Groq output."""
        if not raw_text or not isinstance(raw_text, str):
            raise ValueError("Empty response received from Groq Deployment Agent.")

        cleaned = raw_text.strip()
        if "```" in cleaned:
            m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*(?:```|\Z)', cleaned)
            if m:
                cleaned = m.group(1).strip()

        if not cleaned.startswith('{'):
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end + 1]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON Deployment Report returned by Groq: {str(e)}")

        if not isinstance(parsed, dict):
            raise ValueError("Deployment Report root payload must be a JSON object.")

        return parsed

    def _normalize_status(self, raw_status: str) -> str:
        s = (raw_status or '').strip().lower()
        if 'ready' in s:
            return 'Ready'
        if 'not applicable' in s or s in ('n/a', 'na'):
            return 'Not Applicable'
        if 'missing' in s:
            return 'Missing'
        return 'Needs Review'

    def _detect_code_files(self, code_content: str) -> list:
        """Extracts list of file paths from approved CODE artifact if JSON structured."""
        paths = []
        if not code_content:
            return paths
        clean_str = code_content.strip()
        if "```" in clean_str:
            m = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*(?:```|\Z)', clean_str)
            if m:
                clean_str = m.group(1).strip()
        try:
            arr = json.loads(clean_str)
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict) and item.get('path'):
                        paths.append(str(item['path']).lower())
        except Exception:
            pass
        return paths

    def _validate_and_normalize_report(self, data: Dict[str, Any], code_content: str = "") -> Dict[str, Any]:
        """Validates all 3 required sections and guards readiness statuses against code evidence."""
        required_keys = ['deployment_recommendation', 'deployment_readiness', 'deployment_instructions']
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValueError(f"Malformed Deployment Report schema: missing required section(s) {', '.join(missing)}.")

        rec = data.get('deployment_recommendation')
        checks = data.get('deployment_readiness')
        instr = data.get('deployment_instructions')

        if not isinstance(rec, dict):
            raise ValueError("Malformed Deployment Report: 'deployment_recommendation' must be an object.")
        if not isinstance(checks, list):
            raise ValueError("Malformed Deployment Report: 'deployment_readiness' must be a list.")
        if not isinstance(instr, dict):
            raise ValueError("Malformed Deployment Report: 'deployment_instructions' must be an object.")

        hosting = str(rec.get('hosting_platform') or '').strip()
        db_rec = str(rec.get('database_recommendation') or '').strip()
        explanation = str(rec.get('explanation') or '').strip()
        if not hosting or not db_rec or not explanation:
            raise ValueError("Incomplete 'deployment_recommendation': hosting_platform, database_recommendation, and explanation are required.")

        cfg_reqs = rec.get('config_requirements', [])
        if not isinstance(cfg_reqs, list):
            cfg_reqs = [str(cfg_reqs)] if cfg_reqs else []
        cfg_reqs = [str(c).strip() for c in cfg_reqs if str(c).strip()]

        norm_rec = {
            'hosting_platform': hosting,
            'database_recommendation': db_rec,
            'config_requirements': cfg_reqs,
            'explanation': explanation,
        }

        # Enforce exact 5 checks in deterministic order
        canonical_checks = ['Dependencies', 'Environment Variables', 'Security', 'Database', 'Static Files']
        checks_map = {}
        for item in checks:
            if not isinstance(item, dict):
                continue
            cname = str(item.get('check') or '').strip().lower()
            matched_key = None
            for canon in canonical_checks:
                if canon.lower() in cname or cname in canon.lower():
                    matched_key = canon
                    break
            if matched_key and matched_key not in checks_map:
                checks_map[matched_key] = {
                    'check': matched_key,
                    'status': self._normalize_status(item.get('status', 'Needs Review')),
                    'explanation': str(item.get('explanation') or '').strip() or "No evidence detail supplied; human verification recommended.",
                }

        # Evidence cross-check on structured code files (prevent false 'Ready' when dependency file absent)
        code_paths = self._detect_code_files(code_content)
        has_dep_file = any(
            any(df in p for df in ['requirements.txt', 'package.json', 'pyproject.toml', 'pipfile', 'gemfile', 'pom.xml'])
            for p in code_paths
        )

        norm_checks = []
        for canon in canonical_checks:
            if canon in checks_map:
                entry = checks_map[canon]
            else:
                entry = {
                    'check': canon,
                    'status': 'Missing',
                    'explanation': f"{canon} check was omitted by generation; manual review needed.",
                }

            # If structured code files exist and NO dependency file is present, never claim Dependencies is Ready
            if canon == 'Dependencies' and code_paths and not has_dep_file and entry['status'] == 'Ready':
                entry['status'] = 'Missing'
                entry['explanation'] += " (Adjusted: No dependency manifest such as requirements.txt or package.json detected in approved code artifacts.)"

            norm_checks.append(entry)

        steps_raw = instr.get('steps', [])
        if not isinstance(steps_raw, list) or len(steps_raw) == 0:
            raise ValueError("Incomplete 'deployment_instructions': ordered deployment 'steps' list is required.")
        norm_steps = [str(s).strip() for s in steps_raw if str(s).strip()]

        checklist_raw = instr.get('verification_checklist', [])
        if not isinstance(checklist_raw, list):
            checklist_raw = [str(checklist_raw)] if checklist_raw else []
        norm_checklist = [str(v).strip() for v in checklist_raw if str(v).strip()]
        if not norm_checklist:
            norm_checklist = [
                "Open deployed URL in browser and confirm application loads cleanly.",
                "Verify core functional workflow responds without server or console errors."
            ]

        return {
            'deployment_recommendation': norm_rec,
            'deployment_readiness': norm_checks,
            'deployment_instructions': {
                'steps': norm_steps,
                'verification_checklist': norm_checklist,
            },
        }

    def generate(self, project: Project, feedback: Optional[str] = None) -> str:
        """Generates, validates, and returns a lightweight 3-section JSON Deployment Report."""
        context = self.build_context(project)
        system_prompt = self.get_system_prompt()
        code_content = self._get_approved_artifact_content(project, 'CODE') or ""

        user_prompt = (
            "Please generate the simplified 3-section Deployment Report in valid JSON format "
            "(Deployment Recommendation, 5 Deployment Readiness Checks, Manual Deployment Instructions)."
        )
        if feedback:
            user_prompt += f"\n\nIMPORTANT - Human reviewer feedback on the previous deployment report that you MUST incorporate:\n{feedback}"

        raw_output = self.groq.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            context=context
        )

        parsed_json = self._extract_json(raw_output)
        normalized = self._validate_and_normalize_report(parsed_json, code_content=code_content)
        return json.dumps(normalized, indent=2)

    def _run_local_consistency_checks(self, output: str) -> Dict[str, Any]:
        """Checks structural completeness and status validity locally before Jev call."""
        local_issues = []
        local_warnings = []
        try:
            data = self._extract_json(output)
        except ValueError as e:
            local_issues.append(f"Structural validation failed: {str(e)}")
            return {'valid': False, 'issues': local_issues, 'warnings': local_warnings}

        for sec in ['deployment_recommendation', 'deployment_readiness', 'deployment_instructions']:
            if sec not in data:
                local_issues.append(f"Missing required deployment section: '{sec}'.")

        checks = data.get('deployment_readiness', [])
        valid_statuses = {'Ready', 'Needs Review', 'Missing', 'Not Applicable'}
        if isinstance(checks, list):
            if len(checks) != 5:
                local_warnings.append(f"Expected 5 readiness checks, found {len(checks)}.")
            for c in checks:
                if isinstance(c, dict):
                    st = c.get('status')
                    if st not in valid_statuses:
                        local_issues.append(f"Invalid readiness status '{st}' for check '{c.get('check')}'.")
        else:
            local_issues.append("'deployment_readiness' must be a list of the 5 checks.")

        instr = data.get('deployment_instructions', {})
        if isinstance(instr, dict):
            if not instr.get('steps'):
                local_issues.append("Missing ordered deployment instructions steps.")
            if not instr.get('verification_checklist'):
                local_warnings.append("Post-deployment verification checklist is missing.")

        return {
            'valid': len(local_issues) == 0,
            'issues': local_issues,
            'warnings': local_warnings,
        }

    def validate(self, output: str, project: Project) -> Dict[str, Any]:
        local_check = self._run_local_consistency_checks(output)

        rules = [
            "Verify whether all three sections (Deployment Recommendation, Deployment Readiness checks, Deployment Instructions) are present.",
            "Evaluate the five deployment readiness checks (Dependencies, Environment Variables, Security/DEBUG, Database, Static Files) and check for critical security concerns.",
            "Verify consistency between the recommended hosting/database setup, approved project artifacts, and deployment instructions.",
            "Evaluate overall deployment readiness clarity without claiming automatic deployment execution.",
            "Flag whether human review is required."
        ]
        jev_res = self.jev.validate_artifact(content=output, stage=self.stage_name, rules=rules)

        merged_issues = list(jev_res.get('issues') or []) + local_check['issues']
        merged_warnings = list(jev_res.get('warnings') or []) + local_check['warnings']

        jev_res['issues'] = merged_issues
        jev_res['warnings'] = merged_warnings
        jev_res['valid'] = bool(jev_res.get('valid', True)) and local_check['valid']
        jev_res['requires_human_review'] = True
        return jev_res


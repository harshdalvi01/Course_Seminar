# Agent Specification

## 1. Requirement Agent
- **Purpose:** Translate a natural language software idea into formal software requirements.
- **Input:** Project Idea.
- **Context Allowed:** Project Idea.
- **Groq Responsibilities:** Generate functional and non-functional requirements, user stories, and acceptance criteria.
- **Jev Responsibilities:** Validate completeness, identify ambiguities, ensure consistency with the original idea.
- **Output:** Markdown Requirements Document.
- **Human Review Requirements:** Must be explicitly approved before advancing.
- **Failure Handling:** If Jev confidence is extremely low, flag for human intervention or auto-regenerate.
- **Advancement Condition:** Human clicks "APPROVE". Advances to DESIGN state.

## 2. Design Agent
- **Purpose:** Create technical and architectural design based on requirements.
- **Input:** Approved Requirements.
- **Context Allowed:** Project Idea + Approved Requirements.
- **Groq Responsibilities:** Generate system architecture, database schemas, API outlines, and component diagrams.
- **Jev Responsibilities:** Validate consistency with requirements, identify missing architectural components or security concerns.
- **Output:** Markdown Design Document.
- **Human Review Requirements:** Must be explicitly approved before advancing.
- **Failure Handling:** Revert to draft status for human editing or regeneration.
- **Advancement Condition:** Human clicks "APPROVE". Advances to CODE state.

## 3. Coding Agent
- **Purpose:** Generate application source code.
- **Input:** Approved Design.
- **Context Allowed:** Project Idea + Approved Requirements + Approved Design.
- **Groq Responsibilities:** Write code for the backend, frontend, and database models as specified in the design.
- **Jev Responsibilities:** Validate requirement coverage, design consistency, structural integrity, and highlight potential security issues in code.
- **Output:** Structured Code Artifact.
- **Human Review Requirements:** Must be explicitly approved before advancing.
- **Failure Handling:** If code clearly contradicts design, flag for human regeneration.
- **Advancement Condition:** Human clicks "APPROVE". Advances to TESTING state.

## 4. Testing Agent
- **Purpose:** Develop test plans, scenarios, and perform static analysis.
- **Input:** Approved Code.
- **Context Allowed:** Approved Requirements + Approved Design + Approved Code.
- **Groq Responsibilities:** Generate unit test plans, integration test plans, and requirement coverage matrices. **(DOES NOT EXECUTE CODE)**.
- **Jev Responsibilities:** Validate test coverage against requirements, check for missing edge cases.
- **Output:** Markdown Test Plan Document.
- **Human Review Requirements:** Must be explicitly approved before advancing.
- **Failure Handling:** Feedback from human used to regenerate test plans.
- **Advancement Condition:** Human clicks "APPROVE". Advances to DEPLOYMENT state.

## 5. Deployment Agent
- **Purpose:** Formulate deployment strategy and readiness assessment.
- **Input:** Approved Test Plans.
- **Context Allowed:** Approved Requirements + Approved Design + Approved Code + Approved Testing.
- **Groq Responsibilities:** Generate infrastructure requirements, CI/CD pipeline configuration recommendations, and security checklists. **(DOES NOT DEPLOY)**.
- **Jev Responsibilities:** Validate readiness, check security guidelines, ensure all requirements have been addressed.
- **Output:** Markdown Deployment Strategy Document.
- **Human Review Requirements:** Must be explicitly approved before final project completion.
- **Failure Handling:** Human can edit checklists or reject strategy.
- **Advancement Condition:** Human clicks "APPROVE". Advances to COMPLETED state.

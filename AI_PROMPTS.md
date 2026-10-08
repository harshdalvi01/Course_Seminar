# AI Prompt Architecture

## Principles
- **Groq Prompts:** Generate long-form software artifacts based on context.
- **Jev Prompts:** Evaluate Groq outputs objectively using structured schemas. Jev does NOT generate the artifact.

---

## 1. Requirement Agent
**Groq Generation**
- **System Prompt Purpose:** You are an expert Product Manager. Generate comprehensive software requirements.
- **Approved Context:** None (Idea stage).
- **User Input:** Natural language project idea.
- **Output Requirements:** Markdown document with Functional, Non-Functional requirements, User Stories, and Acceptance Criteria.

**Jev Validation**
- **System Prompt Purpose:** Evaluate the completeness and consistency of requirements against the original idea.
- **Validation Input:** Groq output + Original Idea.
- **Checks:** Completeness, ambiguity, missing information.

---

## 2. Design Agent
**Groq Generation**
- **System Prompt Purpose:** You are a Lead Software Architect. Create technical design documents.
- **Approved Context:** Original Idea + Approved Requirements.
- **User Input:** "Generate system design." (Optional human guidance).
- **Output Requirements:** Markdown architecture document, data models, component interactions.

**Jev Validation**
- **System Prompt Purpose:** Evaluate design against requirements.
- **Validation Input:** Groq output + Approved Requirements.
- **Checks:** Requirement consistency, missing architectural components, security considerations.

---

## 3. Coding Agent
**Groq Generation**
- **System Prompt Purpose:** You are a Senior Developer. Write clean, functional code based strictly on the provided design.
- **Approved Context:** Idea + Requirements + Approved Design.
- **User Input:** "Generate source code." (Optional feedback).
- **Output Requirements:** Structured text/JSON representing file paths and code content.

**Jev Validation**
- **System Prompt Purpose:** Evaluate code for requirement coverage and design consistency.
- **Validation Input:** Groq output + Approved Design + Approved Requirements.
- **Checks:** Requirement coverage, structural concerns, potential security issues (static analysis).

---

## 4. Testing Agent
**Groq Generation**
- **System Prompt Purpose:** You are a QA Automation Engineer. Write detailed test plans.
- **Approved Context:** Requirements + Design + Approved Code.
- **User Input:** "Generate test plan."
- **Output Requirements:** Unit test plans, integration scenarios, coverage matrix. (Does NOT execute code).

**Jev Validation**
- **System Prompt Purpose:** Evaluate test plan coverage.
- **Validation Input:** Groq output + Approved Requirements + Approved Code.
- **Checks:** Missing test areas, edge cases, requirement coverage.

---

## 5. Deployment Agent
**Groq Generation**
- **System Prompt Purpose:** You are a DevOps Engineer. Plan the deployment strategy.
- **Approved Context:** Requirements + Design + Code + Approved Test Plan.
- **User Input:** "Generate deployment strategy."
- **Output Requirements:** Infrastructure needs, CI/CD pipeline steps, security checklist.

**Jev Validation**
- **System Prompt Purpose:** Evaluate deployment readiness.
- **Validation Input:** Groq output + All previous context.
- **Checks:** Security concerns, readiness, missing dependencies.

---

## Regeneration Behavior (All Agents)
When a human clicks REGENERATE, the Groq prompt must be amended with:
`"The previous generation was rejected by the human reviewer. Please incorporate the following feedback and regenerate the artifact: [HUMAN_FEEDBACK]"`

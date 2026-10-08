# Project Context

## 1. Project Objective
Build an academic prototype demonstrating an AI-native software engineering lifecycle where specialized AI agents perform SDLC tasks, Jev validates AI outputs, and humans remain responsible for final decisions.

## 2. SDLC Workflow
The prototype follows a strict, sequential state machine:
User Idea -> Requirement Agent -> Jev Validation -> Human Review -> Design Agent -> Jev Validation -> Human Review -> Coding Agent -> Jev Validation -> Human Review -> Testing Agent -> Jev Validation -> Human Review -> Deployment Agent -> Jev Validation -> Final Human Approval.

## 3. Role of Groq
Groq serves as the **generative engine**. It powers the specialized agents that create the actual software artifacts (requirements documents, design specifications, source code, test plans, and deployment strategies) based on prior context.

## 4. Role of Jev
Jev (TypeSafe AI) serves as the **validation and decision support layer**. It does not generate artifacts; rather, it objectively evaluates Groq's outputs against strict schemas, checks for missing components or security flaws, and provides a confidence score to aid the human reviewer.

## 5. Role of Human Review
Humans provide the **final governance**. The AI proposes and automates, but the human must review the generated artifact alongside Jev's validation report and explicitly click `APPROVE`, `REJECT`, `EDIT`, or `REGENERATE`. The SDLC state only advances upon explicit human approval.

## 6. Artifact/Version Philosophy
All artifacts are strictly **append-only**. Whenever an artifact is generated or a human edits an existing one, a new version is created. Previous versions are never overwritten, ensuring a complete, auditable history of how the software evolved. Unapproved artifacts are quarantined and never passed as context to downstream agents.

## 7. Security Constraints
- AI-generated code must **never** be executed automatically on the server.
- API keys must remain secure and never exposed to the frontend.
- Standard Django security (CSRF, Object-Level Permissions) must be enforced.

## 8. Explicitly Excluded Features
- No automatic deployment.
- No execution of AI-generated source code.
- No automatic installation of generated dependencies.
- No React or unnecessary frontend frameworks.
- No Ollama (using Groq instead).
- No microservices architecture (monolithic Django app only).

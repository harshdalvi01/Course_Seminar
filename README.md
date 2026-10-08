# AI-Native Software Engineering

**Subtitle:** Redesigning the Software Development Lifecycle Around Autonomous AI Agents

## Project Description
This academic prototype demonstrates a novel, AI-native approach to software engineering. Instead of using AI as an ad-hoc coding assistant, this project embeds specialized AI agents directly into the stages of the Software Development Lifecycle (SDLC). 

## Problem & Solution
**Problem:** Traditional software development involves massive manual overhead in drafting requirements, architecture, code, tests, and deployment scripts. Current AI tools assist with snippets but don't autonomously manage the pipeline.
**Solution:** A Django-based system where AI agents autonomously generate artifacts for each SDLC stage based on previous context. Crucially, a secondary AI (Jev) validates outputs, while a Human-in-the-Loop provides final governance, approval, and feedback.

## Architecture
- **Generation:** Groq API (Specialized Agents)
- **Validation:** Jev / TypeSafe AI API (Decision Support)
- **Governance:** Human User (Final Approval)
- **Backend:** Python / Django
- **Database:** SQLite (Append-only versioning)
- **Frontend:** HTML, CSS, Vanilla JS

## Features
- **[PLANNED]** User Authentication and Project Dashboard
- **[PLANNED]** SDLC State Machine (Idea -> Requirements -> Design -> Code -> Testing -> Deployment)
- **[PLANNED]** Requirement Agent
- **[PLANNED]** Design Agent
- **[PLANNED]** Coding Agent
- **[PLANNED]** Testing Agent
- **[PLANNED]** Deployment Agent
- **[PLANNED]** Human-in-the-Loop Controls (Approve, Edit, Reject, Regenerate)
- **[PLANNED]** Strict Artifact Version History

## Setup Instructions
*(Instructions will be added as implementation progresses)*
1. Clone the repository
2. Set up virtual environment
3. Install requirements
4. Configure `.env` with `GROQ_API_KEY` and `JEV_API_KEY`
5. Run migrations
6. Start server

## Limitations
- **No Code Execution:** To ensure safety, AI-generated code is stored as text and never executed on the host server.
- **No Auto-Deployment:** The deployment agent generates strategy documents, not actual infrastructure alterations.
- **Validation Limits:** Jev validation provides decision support and confidence scoring, but does not guarantee mathematical correctness of code.

## Documentation
Please see the following files for detailed specifications:
- `Context.md`
- `ARCHITECTURE.md`
- `AGENT_SPECIFICATION.md`
- `WORKFLOW_SPECIFICATION.md`
- `HITL_SPECIFICATION.md`
- `JEV_VALIDATION.md`
# Workflow Specification

## SDLC States
1. `IDEA`: Initial state when project is created.
2. `REQUIREMENTS`: Working on requirements artifact.
3. `DESIGN`: Working on design artifact.
4. `CODE`: Working on code artifacts.
5. `TESTING`: Working on test plans and static analysis.
6. `DEPLOYMENT`: Working on deployment strategy.
7. `COMPLETED`: Project finished and fully approved.

## State Transitions
The project moves strictly forward upon human approval.

- **IDEA → REQUIREMENTS**
  - Trigger: User submits the project idea.
- **REQUIREMENTS → DESIGN**
  - Trigger: Requirements generated → Jev validated → Human reviews and clicks APPROVE.
- **DESIGN → CODE**
  - Trigger: Design generated → Jev validated → Human reviews and clicks APPROVE.
- **CODE → TESTING**
  - Trigger: Code generated → Jev validated → Human reviews and clicks APPROVE.
- **TESTING → DEPLOYMENT**
  - Trigger: Testing plan generated → Jev validated → Human reviews and clicks APPROVE.
- **DEPLOYMENT → COMPLETED**
  - Trigger: Deployment plan generated → Jev validated → Human reviews and clicks APPROVE.

## Alternate Paths

### Rejection Path
- **Trigger:** Human clicks REJECT.
- **Action:** Artifact is marked as rejected. State does NOT advance. User is required to provide feedback explaining the rejection.

### Regeneration Path
- **Trigger:** Human clicks REGENERATE (often after a rejection).
- **Action:** Groq is called again, passing the previous context PLUS the human's feedback. A new version of the artifact is created and sent to Jev for validation. State remains in current stage awaiting review.

### Editing Path
- **Trigger:** Human clicks EDIT.
- **Action:** Human manually alters the generated text. When saved, a new version of the artifact is created. The older version is preserved. Jev may optionally re-validate the human-edited text. The state remains awaiting review until the human explicitly APPROVES the new version.

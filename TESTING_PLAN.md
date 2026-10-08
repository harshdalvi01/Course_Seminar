# Testing Plan

## Overview
The testing strategy ensures the Django application functions correctly, security boundaries hold, and the complex human-AI workflow operates smoothly.

## Test Categories

### 1. Unit Testing
- Test database models (User, Project, Artifact, Review).
- Ensure relationships and constraints (like append-only versioning) function properly.

### 2. Integration Testing
- Test Django Views and Forms.
- Ensure state transitions in `Project.current_stage` only occur on `APPROVE`.

### 3. Authentication & Authorization Testing
- Verify users can register, login, and logout.
- **Project Ownership:** Ensure User A cannot view, edit, or delete User B's projects.

### 4. AI Service Failure Testing
- Mock Groq API to return 500 errors, timeouts, or invalid responses; ensure graceful UI degradation.
- Mock Jev API failures; ensure the system handles validation failures without crashing.

### 5. Artifact Version & HITL Testing
- Test the EDIT function: assert a new version is created and the old version remains accessible.
- Test the REJECT function: assert state does not advance.
- Test the REGENERATE function: assert new versions are created and feedback is appended.

### 6. Security Testing
- Attempt to execute generated code (should be impossible by design).
- Attempt CSRF attacks on API endpoints.
- Attempt prompt injection in project ideas.

## End-to-End Scenario: Library Management System
This scenario tests the entire SDLC pipeline.

1. **Idea:** Submit idea: "A system to manage books, patrons, and borrowing in a small library."
2. **Requirements:** Trigger Agent -> Jev validates -> Human clicks APPROVE.
3. **Design:** Trigger Agent -> Jev validates -> Human clicks APPROVE.
4. **Code:** Trigger Agent -> Jev validates -> Human clicks EDIT -> Makes minor change -> clicks APPROVE.
5. **Testing:** Trigger Agent -> Jev validates -> Human clicks REJECT with feedback -> REGENERATE -> clicks APPROVE.
6. **Deployment:** Trigger Agent -> Jev validates -> Final Approval.
7. **Verification:** Project marked as COMPLETED. All 5 stages have approved artifacts and preserved version history.

# Jev Validation Specification

## Core Philosophy
**IMPORTANT: Jev is NOT the generation model.** 
Groq handles generation. Jev handles structured validation and decision support. Human makes the final decision. Jev confidence is a decision-support signal and NOT proof of correctness.

## Normalized Internal Validation Structure
Regardless of the raw response from the Jev/TypeSafe API, the Django application will adapt it into the following normalized internal JSON structure for storage and UI presentation:

```json
{
    "valid": true,
    "confidence": 0.94,
    "issues": [
        "Requirement 3 is ambiguous regarding latency."
    ],
    "warnings": [
        "No explicit security requirements defined."
    ],
    "requires_human_review": true
}
```

## Stage-Specific Validation Checks

### 1. REQUIREMENTS
- **Completeness:** Does the document address the core idea?
- **Consistency:** Are there contradictory requirements?
- **Ambiguity:** Are requirements testable and clear?
- **Missing Information:** Are non-functional requirements addressed?
- **Human-Review Recommendation:** Flag if critical business logic is vague.

### 2. DESIGN
- **Requirement Consistency:** Does the design satisfy all approved requirements?
- **Missing Components:** Are database models or API routes missing for defined features?
- **Architectural Concerns:** Is the proposed architecture suitable?
- **Security Concerns:** Are basic security controls designed?
- **Human-Review Recommendation:** Flag if complex custom architecture is proposed.

### 3. CODE
- **Requirement Coverage:** Does the code implement the required features?
- **Design Consistency:** Does the code follow the approved architectural design?
- **Structural Concerns:** Are there syntax errors or major anti-patterns?
- **Potential Security Issues:** (Static Analysis) SQL injection, hardcoded secrets, XSS vulnerabilities.
- **Human-Review Recommendation:** ALWAYS true for code.

### 4. TESTING
- **Requirement Coverage:** Does the test plan cover all functional requirements?
- **Missing Test Areas:** Are edge cases and error states tested?
- **Severity:** Identify critical paths lacking test coverage.
- **Consistency:** Do the tests match the generated code?
- **Human-Review Recommendation:** Flag if critical paths are under-tested.

### 5. DEPLOYMENT
- **Missing Requirements:** Are infrastructure needs fully mapped out?
- **Security Concerns:** Are environment variables and secrets handled securely in the plan?
- **Deployment Readiness:** Is the plan actionable?
- **Consistency:** Does it match the tech stack defined in the design?
- **Human-Review Recommendation:** Flag if production deployment steps look risky.

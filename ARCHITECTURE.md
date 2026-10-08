# Architecture

## Core Architectural Principle
GROQ = GENERATION
JEV = STRUCTURED VALIDATION / DECISION SUPPORT
HUMAN = FINAL GOVERNANCE AND APPROVAL

## System Architecture

```text
+-------------------+       +-----------------------+       +-------------------+
|                   |       |                       |       |                   |
|   User Browser    | <---> |   Django Web Server   | <---> |  SQLite Database  |
|  (HTML/CSS/JS)    |       |   (Python/Views)      |       |  (State/History)  |
|                   |       |                       |       |                   |
+-------------------+       +-----------------------+       +-------------------+
                                       |
                                       |
                            +--------------------+
                            |                    |
                            |   SDLC Workflow    |
                            |   State Machine    |
                            |                    |
                            +--------------------+
                                       |
                                       v
                            +--------------------+
                            |                    |
                            | Specialized Agent  |
                            | (Req/Des/Code/etc) |
                            |                    |
                            +--------------------+
                                 /            \
                                /              \
                        +------------+    +------------+
                        |            |    |            |
                        |  Groq API  |    |  Jev API   |
                        | (Generate) |    | (Validate) |
                        |            |    |            |
                        +------------+    +------------+
```

## User Flow
1. User creates an idea.
2. User clicks "Generate Requirements".
3. System invokes Groq to generate.
4. System invokes Jev to validate Groq's output.
5. System presents output + validation score to User.
6. User Reviews. (Approves, Edits, Rejects, or Regenerates)
7. On Approval, state advances to next stage.

## Data Flow (Approved-Context Flow)
Artifacts build context sequentially. Unapproved artifacts NEVER pass to the next stage.
- **IDEA** -> Requirement Agent
- **IDEA + APPROVED REQ** -> Design Agent
- **IDEA + APPROVED REQ + APPROVED DESIGN** -> Coding Agent
- **APPROVED REQ + APPROVED DESIGN + APPROVED CODE** -> Testing Agent
- **APPROVED REQ + APPROVED DESIGN + APPROVED CODE + APPROVED TESTING** -> Deployment Agent

## Separation of Responsibilities (Groq vs Jev)
**Why are Groq and Jev separate?**
Using the same model for both generation and validation leads to confirmation bias (the model tends to grade its own homework highly). Separating concerns ensures an independent evaluation. 
- **Groq** is tuned for fast, creative, long-form content generation.
- **Jev** is tasked solely with objective, structured decision support, evaluating the generated artifact against specific rules and prior context.

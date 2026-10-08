# API Specification

## Architectural Approach
Since this is a standard Django application with vanilla JavaScript, we will avoid over-engineering a full REST API. Most interactions will use standard Django Views, Forms, and template rendering. 

For asynchronous operations driven by JavaScript (like polling AI generation status or triggering agents without page reloads), we will use lightweight Django JSON endpoints.

## Logical Endpoints

### Authentication
- `GET /login/` - Render login form
- `POST /login/` - Authenticate user
- `GET /register/` - Render registration form
- `POST /register/` - Create user
- `POST /logout/` - End session

### Projects
- `GET /projects/` - List user's projects (Dashboard)
- `GET /projects/create/` - Form to create a new project (Idea stage)
- `POST /projects/create/` - Create project
- `GET /projects/<id>/` - Project detail and SDLC status

### Agents (Async JSON Endpoints)
These endpoints trigger Groq/Jev pipelines and return status.
- `POST /api/projects/<id>/generate/requirements/`
- `POST /api/projects/<id>/generate/design/`
- `POST /api/projects/<id>/generate/code/`
- `POST /api/projects/<id>/generate/testing/`
- `POST /api/projects/<id>/generate/deployment/`
- **Response Format:** `{"status": "success", "artifact_id": 123, "new_version": 2}`

### Artifacts & Reviews (HTML & JSON)
- `GET /projects/<id>/artifacts/<stage>/` - View the current active artifact for a stage.
- `POST /projects/<id>/artifacts/<artifact_id>/review/` - Submit a review.
  - **Payload:** `{"action": "APPROVE|REJECT|REGENERATE", "feedback": "..."}`
- `POST /projects/<id>/artifacts/<artifact_id>/edit/` - Submit human edits, creating a new version.
- `GET /projects/<id>/artifacts/<stage>/history/` - View version history for a specific stage.

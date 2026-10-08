# Database Design

## Overview
The application will use SQLite (initially) with standard Django ORM models. The database needs to maintain users, projects, and a strict version history for all artifacts generated or edited during the SDLC.

## Models

### 1. User
- Handled by Django's built-in `auth.User` model.
- **Fields:** `username`, `email`, `password`, `is_active`, `date_joined`, etc.

### 2. Project
Represents a software project moving through the SDLC.
- **Fields:**
  - `id` (Primary Key)
  - `owner` (ForeignKey to User)
  - `title` (CharField)
  - `idea_description` (TextField)
  - `current_stage` (CharField/Enum: IDEA, REQUIREMENTS, DESIGN, CODE, TESTING, DEPLOYMENT, COMPLETED)
  - `created_at` (DateTimeField)
  - `updated_at` (DateTimeField)
- **Relationships:** Owned by a single User. Contains multiple Artifacts.

### 3. Artifact
Represents a versioned piece of output (Requirements, Design, Code, etc.). 
- **Fields:**
  - `id` (Primary Key)
  - `project` (ForeignKey to Project)
  - `stage` (CharField/Enum: matching SDLC stages)
  - `version_number` (IntegerField)
  - `content` (TextField or JSONField depending on code vs text)
  - `jev_validation_data` (JSONField - stores normalized Jev response)
  - `created_by_ai` (BooleanField)
  - `created_at` (DateTimeField)
- **Constraints & Versioning:** 
  - `(project, stage, version_number)` should be uniquely indexed.
  - **CRITICAL:** Artifacts are append-only. Never overwrite an existing version. If a human edits `Requirements v1`, it creates `Requirements v2`.

### 4. Review
Records human governance actions on a specific artifact.
- **Fields:**
  - `id` (Primary Key)
  - `artifact` (ForeignKey to Artifact)
  - `reviewer` (ForeignKey to User)
  - `action` (CharField/Enum: APPROVE, EDIT, REJECT, REGENERATE)
  - `feedback_notes` (TextField - required if REJECT or REGENERATE)
  - `reviewed_at` (DateTimeField)

## Data Integrity & Ownership
- Projects are strictly isolated by `owner`. Users cannot view or modify projects they do not own.
- When an `APPROVE` review is recorded, the associated `Project.current_stage` advances.

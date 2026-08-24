# API Documentation

This document describes the primary RESTful API endpoints for the B2B SaaS backend.

## 1. Authentication Endpoints

### `POST /api/v1/auth/register`
- **Description**: Registers a new user.
- **Auth**: None
- **Body**: `{"email": "user@example.com", "password": "securepassword"}`
- **Response**: `200 OK` `{"email": "user@example.com"}`

### `POST /api/v1/auth/token`
- **Description**: Authenticates a user and returns a JWT access token.
- **Auth**: None
- **Body** (form-data): `username`, `password`
- **Response**: `200 OK` `{"access_token": "...", "token_type": "bearer"}`
- **Errors**: `401 Unauthorized` for invalid credentials.

## 2. Organization Endpoints

### `POST /api/v1/organizations`
- **Description**: Creates a new organization. The creator is automatically assigned the `OWNER` role.
- **Auth**: Required
- **Body**: `{"name": "Acme Corp"}`
- **Response**: `200 OK` Organization details.

### `GET /api/v1/organizations`
- **Description**: Lists all organizations where the current user is a member.
- **Auth**: Required
- **Response**: `200 OK` List of organizations.

### `PUT /api/v1/organizations/{org_id}/roles`
- **Description**: Modifies the RBAC role of a member within an organization.
- **Auth**: Required
- **RBAC Role**: `OWNER` or `ADMIN`
- **Body**: `{"user_id": "<uuid>", "role": "MEMBER"}`
- **Response**: `200 OK`
- **Errors**: `403 Forbidden` if attempting to modify the sole `OWNER` or lacking permissions.

## 3. Project Endpoints

### `POST /api/v1/organizations/{org_id}/projects`
- **Description**: Creates a new project inside an organization.
- **Auth**: Required
- **RBAC Role**: `OWNER`, `ADMIN`, or `MEMBER`
- **Body**: `{"name": "Q3 Marketing", "description": "Campaign tasks"}`
- **Response**: `200 OK` Project details.

### `GET /api/v1/organizations/{org_id}/projects`
- **Description**: Lists all projects in the organization.
- **Auth**: Required
- **RBAC Role**: `OWNER`, `ADMIN`, `MEMBER`, or `VIEWER`
- **Response**: `200 OK` Paginated list of projects.

## 4. Task Endpoints

### `POST /api/v1/organizations/{org_id}/projects/{project_id}/tasks`
- **Description**: Creates a new task.
- **Auth**: Required
- **RBAC Role**: `OWNER`, `ADMIN`, or `MEMBER`
- **Body**: `{"title": "Write Copy", "status": "TODO", "priority": "HIGH", "assignee_id": "<uuid>"}`
- **Validation**: Enforces that `assignee_id` is an active member of the organization.
- **Response**: `200 OK` Task details (starts at `version: 1`).

### `PUT /api/v1/organizations/{org_id}/projects/{project_id}/tasks/{task_id}`
- **Description**: Updates a task (Supports Optimistic Concurrency).
- **Auth**: Required
- **RBAC Role**: `OWNER`, `ADMIN`, or `MEMBER`
- **Body**: `{"title": "New Title", "version": 1}`
- **Response**: `200 OK` Updated task (with `version: 2`).
- **Errors**: `409 Conflict` if the provided version does not match the database version.

## 5. Report Endpoints

### `POST /api/v1/organizations/{org_id}/reports`
- **Description**: Triggers an asynchronous report generation background job.
- **Auth**: Required
- **RBAC Role**: `OWNER`, `ADMIN`, or `MEMBER`
- **Headers**: `Idempotency-Key` (Optional, recommended)
- **Response**: `202 Accepted` `{"report_id": "<uuid>", "status": "PENDING"}`
- **Behavior**: Queues a Celery task. If an identical `Idempotency-Key` exists, returns the existing report instead of queueing a duplicate.

### `GET /api/v1/organizations/{org_id}/reports/{report_id}`
- **Description**: Fetches the status and data of a background report.
- **Auth**: Required
- **RBAC Role**: `OWNER`, `ADMIN`, `MEMBER`, or `VIEWER`
- **Response**: `200 OK` containing `status` (`PENDING`, `COMPLETED`, `FAILED`) and `data` (JSON output if completed).

## 6. Health & Readiness Endpoints

### `GET /health`
- **Description**: Liveness probe.
- **Auth**: None
- **Response**: `200 OK` `{"status": "ok"}`

### `GET /ready`
- **Description**: Readiness probe evaluating Postgres and Redis connectivity.
- **Auth**: None
- **Response**: 
  - `200 OK` if all dependencies are reachable.
  - `503 Service Unavailable` if a critical dependency is down.

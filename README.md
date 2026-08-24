# B2B SaaS Backend

A production-oriented, multi-tenant B2B SaaS backend built as a **modular monolith** using FastAPI, PostgreSQL, Redis, Celery, and Docker.

The project focuses on backend engineering challenges commonly found in SaaS systems, including **multi-tenancy, RBAC, concurrent updates, background processing, caching, rate limiting, API reliability, and automated testing**.

---

## Problem Statement

B2B SaaS applications need to support multiple organizations while keeping their data strictly isolated.

At the same time, backend systems must handle concurrent requests, authorization, background workloads, retries, caching, and database consistency without introducing unnecessary distributed-system complexity.

This project addresses these requirements using a **modular monolith architecture**: different business domains are logically separated inside a single deployable backend.

This provides simpler development and deployment while keeping the codebase structured for future scaling.

---

## Key Features

### Multi-Tenancy

- Organization-based tenant isolation.
- Tenant context is resolved through FastAPI dependencies.
- Database queries are scoped to the authenticated organization.
- Includes automated tests for cross-tenant access prevention.

### Role-Based Access Control

Supports hierarchical organization roles:

- `OWNER`
- `ADMIN`
- `MEMBER`
- `VIEWER`

Authorization checks are enforced at the API layer based on the user's organization membership and role.

### Optimistic Concurrency Control

Tasks use version-based concurrency control to prevent lost updates when multiple requests modify the same resource.

The API detects stale versions and rejects conflicting updates instead of silently overwriting data.

### API Idempotency

Idempotency mechanisms prevent duplicate execution of expensive operations when clients retry requests or send repeated requests.

This is particularly useful for background report generation.

### Background Processing

Heavy report-generation operations are executed asynchronously using:

- Celery
- Redis as the message broker

This keeps API requests responsive while long-running work is processed by workers.

### Redis Caching

Redis is used for caching frequently accessed task data.

Cache keys are tenant-aware to prevent data from one organization being returned to another organization.

### Rate Limiting

A Redis-backed sliding-window rate limiter protects API endpoints from excessive requests.

### Reliability

The backend includes mechanisms for:

- Request retries
- Idempotent operations
- Concurrency control
- Database transactions
- Tenant isolation
- Background task processing

### Production-Oriented Infrastructure

The project includes:

- Docker and Docker Compose
- PostgreSQL
- Redis
- Celery workers
- Nginx reverse proxy
- Alembic database migrations
- Structured logging
- Request ID tracing
- GitHub Actions CI

---

## Architecture

The system follows a **modular monolith** architecture.

```text
                    Client
                      |
                      v
                  +-------+
                  | Nginx |
                  +---+---+
                      |
                      v
                +-----------+
                |  FastAPI  |
                |  Backend  |
                +-----+-----+
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
      PostgreSQL    Redis      Celery
      Database      Cache      Workers
          |                       |
          |                       v
          |                 Background Jobs
          |
          v
      Tenant Data
      & Business Data
```

The application is internally organized into:

```text
app/
├── api/          # API routes, dependencies, rate limiting
├── core/         # Configuration, security, logging, Redis, Celery
├── db/           # Database engine and session management
├── models/       # SQLAlchemy ORM models
├── schemas/      # Pydantic request/response schemas
└── tasks/        # Celery background tasks
```

For detailed architecture and design decisions, see:

- [Architecture](docs/architecture.md)
- [System Design](docs/system_design.md)
- [Database Design](docs/database.md)
- [Design Decisions](docs/design_decisions.md)
- [Engineering Trade-offs](docs/tradeoffs.md)

---

## Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI |
| Language | Python 3.12 |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Cache / Broker | Redis 7 |
| Background Jobs | Celery 5 |
| Authentication | JWT |
| Password Hashing | bcrypt / Passlib |
| Reverse Proxy | Nginx |
| Containers | Docker / Docker Compose |
| Testing | Pytest |
| Load Testing | Locust |
| CI/CD | GitHub Actions |

---

## Project Structure

```text
.
├── app/
│   ├── api/
│   │   ├── v1/
│   │   ├── deps.py
│   │   └── rate_limit.py
│   │
│   ├── core/
│   │   ├── celery.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── redis.py
│   │   └── security.py
│   │
│   ├── db/
│   ├── models/
│   ├── schemas/
│   └── tasks/
│
├── alembic/
│   └── versions/
├── nginx/
├── tests/
├── docs/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── requirements.txt
├── requirements-dev.txt
├── Makefile
└── README.md
```

---

## Getting Started

### 1. Clone the Repository

```bash
git clone <repository-url>
cd b2b-saas-backend
```

### 2. Configure Environment Variables

Copy the example configuration:

```bash
cp .env.example .env
```

Update `.env` with appropriate database credentials and a secure secret key.

For example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Do not commit `.env` to the repository.

---

## Running the Application

### Development

Start the development stack:

```bash
docker-compose up --build
```

Apply database migrations:

```bash
docker-compose exec backend alembic upgrade head
```

The API will be available at:

```text
http://localhost:8000
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

---

## Production-Style Deployment

The production configuration runs the backend behind Nginx and keeps internal services isolated.

Start the production stack:

```bash
docker-compose -f docker-compose.prod.yml up --build -d
```

Check service status:

```bash
docker-compose -f docker-compose.prod.yml ps
```

Apply migrations:

```bash
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

The API is exposed through Nginx at:

```text
http://localhost
```

Interactive API documentation:

```text
http://localhost/docs
```

To stop the stack:

```bash
docker-compose -f docker-compose.prod.yml down
```

---

## Example API Flow

A typical user workflow is:

```text
Register
   ↓
Login
   ↓
Receive JWT
   ↓
Create / Join Organization
   ↓
Create Project
   ↓
Create Tasks
   ↓
Manage Tasks
   ↓
Generate Reports
   ↓
Celery processes report asynchronously
```

The API can be explored interactively through FastAPI's Swagger UI at:

```text
http://localhost/docs
```

---

## Database Migrations

Database schema changes are managed using Alembic.

Create a migration:

```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:

```bash
alembic upgrade head
```

Check the current migration:

```bash
alembic current
```

---

## Testing

The project includes tests covering:

- Authentication
- Organizations
- Projects
- Tasks
- Database behavior
- Redis integration
- Celery tasks
- Tenant isolation
- Reliability controls
- Report APIs

Run the test suite:

```bash
pytest -v
```

Run with coverage:

```bash
pytest -v --cov=app --cov-report=term-missing
```

Current test suite:

- **59 tests**
- **96% code coverage**

---

## Load Testing

Locust is included for concurrent API testing.

The load-testing configuration is available in:

```text
locustfile.py
```

The performance experiments were performed locally to evaluate API throughput, latency, caching behavior, and database performance.

Measured results are documented in:

- [Performance Baseline](docs/performance_baseline.md)
- [Performance Report](docs/performance_report.md)

---

## Performance

During local load testing, the system achieved approximately:

- **~28 requests/second** under the tested mixed workload.
- Cached `GET /tasks`: approximately **140 ms P95**.
- Database-backed `GET /tasks?status`: approximately **440 ms P95**.

A composite index on:

```text
(project_id, status)
```

was introduced for task filtering.

Redis caching was also used to reduce repeated database reads.

> These measurements are environment-specific and should not be interpreted as production capacity guarantees.

---

## CI/CD

GitHub Actions automatically performs:

- Dependency installation
- Test execution
- Coverage checks
- Formatting / validation
- PostgreSQL and Redis service setup
- Production Docker build validation

Workflow configuration:

```text
.github/workflows/ci.yml
```

---

## Security Considerations

The project implements several backend security mechanisms:

- JWT-based authentication
- Password hashing
- Role-based authorization
- Tenant-level data isolation
- Rate limiting
- Input validation through Pydantic
- Environment-based secret configuration
- Nginx reverse proxy
- Request ID tracing

Security-related design notes are available in:

- [Security Review](docs/security_review.md)

---

## Engineering Challenges

The project focuses on several problems that are common in real backend systems:

### 1. Preventing Cross-Tenant Data Access

Every authenticated request resolves its organization context and restricts database access accordingly.

### 2. Handling Concurrent Updates

Version-based optimistic concurrency prevents stale clients from overwriting newer task updates.

### 3. Making Expensive Operations Asynchronous

Report generation is moved to Celery workers instead of blocking API requests.

### 4. Controlling Duplicate Requests

Idempotency mechanisms protect expensive operations from duplicate execution caused by retries.

### 5. Reducing Database Load

Redis caching and database indexes are used to improve frequently accessed operations.

### 6. Keeping the Architecture Simple

A modular monolith was chosen instead of prematurely splitting the system into microservices.

This keeps deployment and transaction management simpler while maintaining clear module boundaries.

---

## Documentation

Additional engineering documentation:

- [System Architecture](docs/architecture.md)
- [System Design](docs/system_design.md)
- [Database Schema](docs/database.md)
- [API Documentation](docs/api.md)
- [Design Decisions](docs/design_decisions.md)
- [Engineering Trade-offs](docs/tradeoffs.md)
- [Deployment Guide](docs/deployment.md)
- [Security Review](docs/security_review.md)
- [Performance Baseline](docs/performance_baseline.md)
- [Performance Report](docs/performance_report.md)

---

## Project Status

The project is implemented as a **production-oriented backend engineering project** demonstrating practical concepts in:

- Backend development
- REST APIs
- Database design
- Multi-tenancy
- Authentication and authorization
- Concurrency control
- Distributed background processing
- Caching
- Rate limiting
- Testing
- Containerization
- CI/CD
- Performance testing


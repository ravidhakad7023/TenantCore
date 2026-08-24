# Deployment Documentation

This document describes the production deployment procedures for the B2B SaaS Application.

## Architecture

The production architecture isolates internal services from the public internet using an Nginx reverse proxy.

```
Client
  ↓ (HTTP:80)
Nginx (Reverse Proxy)
  ↓ (HTTP:8000)
FastAPI (Backend Application)
  ↓ (TCP:5432 / TCP:6379)
PostgreSQL / Redis
  ↓
Celery Worker (Background Jobs)
```

## Prerequisites

- Docker
- Docker Compose
- `openssl` (for secret generation)

## Environment Variables

You MUST configure the following environment variables in your production environment (e.g. via a `.env` file or cloud secrets manager).

- `POSTGRES_USER`: The PostgreSQL user
- `POSTGRES_PASSWORD`: The PostgreSQL password
- `POSTGRES_DB`: The database name
- `SECRET_KEY`: A cryptographically secure random string. **Never** use the default development key.
  - Generate via: `openssl rand -hex 32`
- `DEBUG`: Must be set to `False` in production.

See `.env.example` for the complete list.

## Production Docker Startup

To start the environment securely in a production-like setup:

```bash
docker-compose -f docker-compose.prod.yml up --build -d
```
*Note: This command will not expose PostgreSQL or Redis directly to the host machine. Only Nginx is exposed on port 80.*

## Database Migration

Ensure migrations are applied before the backend serves traffic:

```bash
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Health Checks

- **Liveness**: `GET /health` (Verifies the FastAPI process is running).
- **Readiness**: `GET /ready` (Verifies the application can connect to both PostgreSQL and Redis). 
Docker healthchecks are natively configured in the `docker-compose.prod.yml` to automatically restart unhealthy containers.

## CI Pipeline

A GitHub Actions workflow is provided in `.github/workflows/ci.yml`. It runs automatically on push and pull requests to `main` and verifies:
1. Python Lints/Tests
2. Database / Redis Dependencies
3. Docker Production Build Success

## Logs

Structured JSON logging is enabled by default to allow easy ingestion into platforms like ELK, Datadog, or AWS CloudWatch. Each log includes a `request_id` for correlation.

```bash
# View backend logs
docker-compose -f docker-compose.prod.yml logs -f backend
```

## Limitations

### LOCAL VERIFIED
The infrastructure described in `docker-compose.prod.yml` and `nginx/nginx.conf` has been successfully verified locally. The containers build correctly, Nginx proxies requests appropriately, and health checks ensure proper startup ordering.

### DEPLOYMENT READY
The repository is deployment-ready for standard IaaS/PaaS providers (e.g. AWS EC2, DigitalOcean) using `docker-compose`. 

**However**, this setup is not a managed cloud deployment (like Kubernetes or AWS ECS). For a fully scalable, enterprise deployment, one would typically:
- Move PostgreSQL to a managed database (e.g. AWS RDS).
- Move Redis to a managed cache (e.g. AWS ElastiCache).
- Extract Nginx for a managed load balancer (e.g. AWS ALB).
- Enforce HTTPS/TLS via certbot or load balancer termination.

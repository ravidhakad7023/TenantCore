# Design Decisions

This document outlines the core technical decisions made during the architecture of this B2B SaaS platform.

## Why FastAPI?
FastAPI was chosen over Django or Flask because of its native Pydantic validation, excellent auto-generated OpenAPI documentation, and high performance. The dependency injection system (`Depends()`) is perfectly suited for extracting multi-tenant contexts and RBAC roles cleanly at the route level without writing verbose middleware.

## Why PostgreSQL (and why it remains the Source of Truth)?
PostgreSQL 15 provides robust ACID compliance, JSONB support, and powerful indexing. We strictly rely on Postgres as the *Single Source of Truth*. Even though Celery tasks and caches use Redis, the actual application state (including background job completion status) is always written back to Postgres. This prevents split-brain scenarios where the cache or message broker disagrees with the database.

## Why SQLAlchemy?
SQLAlchemy 2.0 provides a strictly typed, synchronous ORM pattern that easily integrates with FastAPI. While asynchronous SQL (e.g. `asyncpg`) is popular, synchronous SQLAlchemy paired with FastAPI's thread pool executor provides exceptional performance for our workload while maintaining predictable session lifecycles and easier debugging.

## Why a Modular Monolith?
Microservices often introduce network latency, distributed transaction failures, and complex deployment pipelines prematurely. We adopted a **Modular Monolith**:
- Code is logically isolated into domains (`organizations`, `projects`, `tasks`).
- Data is strictly isolated by `organization_id`.
- The system is deployed as a single unit, drastically reducing operational overhead while preserving the ability to split into microservices later if a specific domain genuinely requires independent scaling.

## Why Redis for both Cache and Celery Broker?
To reduce infrastructure complexity, Redis serves dual purposes. Using Kafka or RabbitMQ would introduce an unnecessary maintenance burden for the current volume of background jobs. Redis is more than capable of acting as a message broker for Celery while simultaneously providing fast key-value lookups for our rate limiter and API caching layers. 

## Why tenant IDs in Cache Keys?
Cache leakage is a critical vulnerability in multi-tenant systems. By strictly embedding the `organization_id` into every Redis cache key (e.g., `org:{org_id}:tasks`), we guarantee that a cache hit for one tenant can never accidentally return data belonging to another.

## Why Optimistic Concurrency Control (OCC)?
In a collaborative SaaS environment, multiple users might edit the same `Task` simultaneously. Pessimistic locking (e.g. `SELECT FOR UPDATE`) locks database rows, reducing throughput and risking deadlocks. We chose **Optimistic Concurrency Control**:
- Every task has a `version` integer.
- Updates require the client to send the `version` they are editing.
- If the `version` in the database has incremented since the client fetched it, the API returns a `409 Conflict`.
- This pushes the resolution logic to the client (who can seamlessly retry or merge), keeping the database blazingly fast.

## Why API Idempotency?
Background jobs like generating reports are computationally expensive. Without idempotency, a client clicking "Generate" multiple times (or network retries) would queue identical, redundant jobs, consuming worker resources. 
- The client passes an `Idempotency-Key` header.
- The backend relies on a database `UNIQUE` constraint `(organization_id, idempotency_key)` on the `organization_reports` table.
- If a duplicate request arrives, Postgres throws a unique violation, which we catch and safely return the existing report reference instead of queueing a new job.

## Why Nginx?
FastAPI (via Uvicorn) should never be exposed directly to the public internet because Uvicorn is an ASGI server, not a hardened HTTP proxy. Nginx buffers slow clients, strips malicious headers, handles HTTPS termination (in production), and safely reverse-proxies requests to the internal Docker network.

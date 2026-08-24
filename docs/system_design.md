# System Design Preparation

This document outlines key talking points for discussing the system design of this B2B SaaS architecture in technical interviews.

## 1. Architecture & Scaling
**Q: Why a Modular Monolith instead of Microservices?**
A: To minimize operational complexity early on. By enforcing strict module boundaries (e.g., separating `organizations`, `projects`, `tasks`) and avoiding cross-module database joins where possible, the codebase is prepared to be split into microservices if one domain requires independent scaling. Right now, a monolith avoids network latency and split-brain failures.

**Q: How would this system handle 10x traffic?**
A: 
- **API Tier**: FastAPI scales horizontally very well. We would place an Auto-Scaling Group of API containers behind a Load Balancer (e.g. AWS ALB). 
- **Database**: PostgreSQL would be vertically scaled first, followed by deploying Read-Replicas to offload `GET` requests.
- **Workers**: Celery workers can scale horizontally by adding more containers consuming from the Redis queue.

## 2. Database Design & Optimization
**Q: Why use these specific indexes?**
A: Composite indexes (like `(project_id, status)`) were chosen based on query access patterns. Our API frequently filters tasks within a specific project by status. Without this, Postgres would perform a sequential scan.

**Q: How would you handle millions of tasks per organization?**
A: We would implement **Database Partitioning** on the `tasks` table, partitioning by `organization_id` (or a hash of it). This ensures that a query scoped to a specific tenant only scans that tenant's physical partition, keeping index trees shallow and reads fast.

## 3. Caching & Stale Data
**Q: How does cache invalidation work here?**
A: Cache invalidation is notoriously difficult. We mitigate stale data by namespacing keys (e.g., `org:{org_id}:projects`) and immediately issuing a Redis `DEL` command on relevant namespaces whenever a `POST`, `PUT`, or `DELETE` request mutates data in that scope.

**Q: How do you handle a Cache Stampede?**
A: Currently, if the cache expires, multiple concurrent users might trigger identical database queries. To prevent a stampede under high load, we would implement **Mutex Locking** (e.g., Redis SETNX) so only the first request queries the DB and repopulates the cache, while the others briefly wait.

## 4. Background Jobs & Fault Tolerance
**Q: What happens if a Celery worker crashes mid-task?**
A: Celery workers utilize message acknowledgments (`ACK`). The message is not removed from Redis until the worker finishes and ACKs. If the worker crashes, the broker restores the message, and another worker picks it up.

**Q: How do you prevent identical jobs from running twice?**
A: Database-level **Idempotency**. We require clients to send an `Idempotency-Key` header. We map this to a unique constraint in Postgres: `(organization_id, idempotency_key)`. If a duplicate job is requested, Postgres throws a collision error, safely preventing duplicate queueing.

## 5. Concurrency Control
**Q: How does OCC (Optimistic Concurrency Control) prevent lost updates?**
A: When two users edit a Task, pessimistic locking (`SELECT FOR UPDATE`) would lock the row, blocking the second user and killing throughput. With OCC, each row has a `version`. 
1. Both users fetch version `1`. 
2. User A saves. The database checks `WHERE version = 1` and updates it to `2`. 
3. User B saves. The database checks `WHERE version = 1`. 
4. Since the version is now `2`, no rows are updated. The backend detects this and throws a `409 Conflict`, forcing User B to fetch the fresh data. 
This guarantees consistency while keeping the DB lock-free.

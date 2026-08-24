# Engineering Trade-offs

Every architectural decision involves balancing benefits against costs. Below are the primary trade-offs made in this project.

## Modular Monolith vs Microservices
- **Trade-off**: We chose a Modular Monolith instead of Microservices. 
- **Cost**: If a single endpoint requires massive CPU scaling (e.g. video rendering), the entire backend application must be scaled horizontally, which is less resource-efficient than scaling a specialized microservice. 
- **Benefit**: We avoided the massive operational overhead of managing distributed transactions, network latency between internal services, API gateways, and multi-repo CI/CD pipelines. The tenant boundaries remain strict, but development velocity is significantly higher.

## PostgreSQL as Source of Truth vs Distributed Stores
- **Trade-off**: We relied purely on PostgreSQL for state, bypassing NoSQL or purely distributed databases (like Cassandra).
- **Cost**: Vertical scaling of the master database is ultimately bound by single-machine hardware limits (though read-replicas could be added later).
- **Benefit**: Unparalleled ACID compliance and relational integrity. Because this is a B2B SaaS application, data consistency (e.g., ensuring a Task accurately maps to a Project and Organization) is vastly more important than extreme horizontal write-scaling.

## Redis Caching vs Invalidation Complexity
- **Trade-off**: Caching API responses in Redis significantly improves read latency.
- **Cost**: Cache invalidation is one of the hardest problems in software engineering. We had to implement strict lifecycle hooks to clear caches whenever underlying records mutate. If a cache clearance fails, users might see stale data.
- **Benefit**: Read performance improved by nearly 60% for list endpoints, saving expensive database cycles. 

## Celery vs Synchronous Processing
- **Trade-off**: Using Celery for background jobs (like reports) instead of executing them within the HTTP request cycle.
- **Cost**: Adds operational complexity. We must maintain a separate Celery worker container, configure a message broker (Redis), and implement database polling endpoints so clients can check job status.
- **Benefit**: The web workers remain free to serve immediate API requests. Long-running jobs do not risk hitting Nginx or FastAPI timeouts.

## Optimistic Concurrency Control (OCC) vs Pessimistic Locking
- **Trade-off**: We implemented OCC (`version` tracking) instead of Pessimistic Locking (`SELECT FOR UPDATE`).
- **Cost**: The client must handle `409 Conflict` errors and retry if someone else updated the record milliseconds before them.
- **Benefit**: Database rows are never locked, maximizing read/write throughput and completely eliminating the risk of database deadlocks during high traffic. 

## Docker Compose vs Kubernetes
- **Trade-off**: We provide a production-ready `docker-compose.prod.yml` instead of a Kubernetes Helm chart.
- **Cost**: Docker Compose lacks native auto-scaling, self-healing node reallocation, and rolling zero-downtime deployments natively compared to K8s.
- **Benefit**: Immediate, understandable deployment for a single Virtual Machine. The system is "deployment ready" for an IaaS environment without the massive learning curve and infrastructure cost of a managed K8s cluster.

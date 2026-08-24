# Performance Baseline

This document captures the baseline performance metrics of the B2B SaaS API *before* optimizations were applied during Phase 11.

## Test Environment
- **Workload Generator**: Locust (Local Execution)
- **Simulated Users**: 10
- **Duration**: ~1 minute

## Measured Workload Metrics
The benchmark simulated a realistic mix of CRUD operations across Authentication, Organizations, Projects, Tasks, and Reports.

- **Total Requests**: 1714
- **Throughput**: ~29 Requests Per Second (RPS)
- **Error Rate**: ~4.7% (82 failures, specifically on `GET /projects` due to lack of DB pagination)

## Latency Breakdown (Pre-Optimization)

| Endpoint | Median | Average | P95 | P99 |
|----------|--------|---------|-----|-----|
| `GET /tasks` | 21ms | 103ms | 870ms | 1200ms |
| `GET /tasks?status` | 20ms | 154ms | 1100ms | 1500ms |
| `GET /tasks/{id}` | 17ms | 73ms | 560ms | 1100ms |
| **Aggregated** | **26ms** | **141ms** | **590ms** | **1200ms** |

## Identified Bottlenecks
1. **High P95/P99 Latency**: Read-heavy endpoints like fetching tasks with status filters experienced severe long-tail latency (up to 1500ms) under concurrent load.
2. **Missing Indexes**: Fetching tasks by `project_id` and `status` required sequential table scans in Postgres.
3. **Repeated DB Queries**: Uncached, identical reads (like fetching all tasks for a project) hit the database on every request.
4. **Endpoint Failures**: The `GET /projects` endpoint threw 500 errors under load because it attempted to serialize massive query sets synchronously.

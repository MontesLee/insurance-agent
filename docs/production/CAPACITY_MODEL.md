# Capacity Model — Phase 21 (all numbers ASSUMPTION)

## Load Scenarios

| Scenario | Cases/day | Peak concurrent | Workers | Notes |
|---|---|---|---|---|
| Pilot | 100 | 10 | 2 | Single PostgreSQL, no Redis |
| Growth | 500 | 50 | 5 | Single PostgreSQL, evaluate Redis |
| Scale | 1,000 | 100 | 10 | Read replica, Redis cache |
| Large | 10,000 | 1,000 | 30+ | Multi-AZ, Redis, queue partitioning |

All numbers are ASSUMPTIONS based on typical insurance-advisor
workloads. No production benchmark data exists.

## Per-Case Resource Estimate (ASSUMPTION)

| Resource | Per case | 100/day | 10K/day |
|---|---|---|---|
| DB rows (tasks) | ~15 | 1.5K/day | 150K/day |
| DB rows (events) | ~100 | 10K/day | 1M/day |
| DB rows (artifacts) | ~50 | 5K/day | 500K/day |
| Object Storage | ~1 MB | 100 MB/day | 10 GB/day |
| LLM calls | ~5-20 (skill-dependent) | 500-2K/day | 50-200K/day |
| Knowledge searches | ~5 | 500/day | 50K/day |
| Report size | ~10-100 KB | 1-10 MB/day | 100 MB-1 GB/day |

## Bottleneck Analysis (ASSUMPTION)

| Scale | First bottleneck | Second bottleneck |
|---|---|---|
| 100/day | None (single instance) | — |
| 500/day | PostgreSQL connection pool | LLM rate limit |
| 1K/day | Synchronous LLM latency | DB write throughput |
| 10K/day | All of the above + queue depth | Multi-AZ replication lag |

## ASSUMPTION Labels

Every number above is an ASSUMPTION — not a benchmark result.
Real capacity planning requires load testing with representative
data and actual LLM providers.

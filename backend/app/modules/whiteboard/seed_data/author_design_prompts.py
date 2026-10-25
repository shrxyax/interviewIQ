"""
One-off authoring script: produces design_prompts.json (180 cards, 18
subtopics x 10). 20 cards are "simulatable" (full requirements + starter
graph, wired into the whiteboard engine); the rest are lightweight
browsing cards (title/scenario/tags only), matching the DSA sheet's
breadth-vs-depth split.

Run: python -m app.modules.whiteboard.seed_data.author_design_prompts
"""

import json
from pathlib import Path

OUT_PATH = Path(__file__).parent / "design_prompts.json"

SUBTOPICS = [
    ("basics", "Fundamentals & Approach"),
    ("scaling", "Scaling"),
    ("consistency_patterns", "Consistency Patterns"),
    ("availability_patterns", "Availability Patterns"),
    ("background_jobs", "Background Jobs"),
    ("dns", "Domain Name System"),
    ("cdn", "Content Delivery Networks"),
    ("load_balancing", "Load Balancing"),
    ("application_layer", "Application Layer & Microservices"),
    ("databases", "Databases"),
    ("caching", "Caching"),
    ("asynchronism", "Asynchronism & Queues"),
    ("idempotency", "Idempotent Operations"),
    ("communication", "Communication Protocols"),
    ("performance_antipatterns", "Performance Antipatterns"),
    ("cloud_patterns", "Cloud Design Patterns"),
    ("reliability", "Reliability & Fault Tolerance"),
    ("monitoring", "Monitoring & Observability"),
]
SUBTOPIC_NAME = dict(SUBTOPICS)


# --------------------------------------------------------------------------
# Graph-building helpers for the 20 simulatable prompts
# --------------------------------------------------------------------------

def node(id_, type_, label, replicas=1, **params):
    p = {"replicas": replicas, **params}
    return {"id": id_, "type": type_, "label": label, "params": p}


def edge(src, dst, fraction=1.0, kind="sync"):
    return {"src": src, "dst": dst, "fraction": fraction, "kind": kind}


def graph(nodes, edges):
    return {"nodes": nodes, "edges": edges}


def reqs(peak_rps, read_ratio=0.8, p99_slo_ms=300, availability_slo=0.999, growth_per_month=0.10):
    return {
        "peak_rps": peak_rps,
        "read_ratio": read_ratio,
        "p99_slo_ms": p99_slo_ms,
        "availability_slo": availability_slo,
        "growth_per_month": growth_per_month,
    }


SIMULATABLE = []


def add_sim(subtopic_id, title, scenario, difficulty, tags, requirements, starter_graph):
    SIMULATABLE.append(
        {
            "subtopic_id": subtopic_id,
            "title": title,
            "scenario": scenario,
            "difficulty": difficulty,
            "tags": tags,
            "simulatable": True,
            "requirements": requirements,
            "starter_graph": starter_graph,
        }
    )


# 1. basics -----------------------------------------------------------------
add_sim(
    "basics",
    "Design a URL Shortener",
    "Design a service that takes a long URL and returns a short code that redirects to it. "
    "Reads (redirects) vastly outnumber writes (new shortlinks). Start simple, then make it survive real load.",
    "Easy",
    ["read-heavy", "caching", "hashing"],
    reqs(peak_rps=20_000, read_ratio=0.95, p99_slo_ms=150, availability_slo=0.999, growth_per_month=0.15),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Shortener API", replicas=2),
            node("cache", "cache", "Redirect Cache", hit_ratio=0.85),
            node("db", "sql_primary", "URL Mapping DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache"),
            edge("cache", "db", fraction="miss"),
        ],
    ),
)

# 2. scaling ------------------------------------------------------------------
add_sim(
    "scaling",
    "Design a News Feed Service at Scale",
    "Design the backend that assembles a user's home feed from the people they follow. At small scale a simple "
    "query works; at scale, fan-out and caching dominate the design.",
    "Hard",
    ["fan-out", "caching", "queueing"],
    reqs(peak_rps=40_000, read_ratio=0.9, p99_slo_ms=400, availability_slo=0.995, growth_per_month=0.20),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Feed API", replicas=3),
            node("cache", "cache", "Feed Cache", hit_ratio=0.75),
            node("db", "sql_primary", "Posts DB"),
            node("queue", "queue", "Fan-out Queue"),
            node("worker", "worker", "Fan-out Worker", replicas=2),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache", fraction=0.9),
            edge("cache", "db", fraction="miss"),
            edge("api", "queue", fraction=0.1, kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 3. consistency_patterns -----------------------------------------------------
add_sim(
    "consistency_patterns",
    "Design a Leaderboard Service with Eventual Consistency",
    "Design a game leaderboard that accepts score updates constantly but only needs to show a consistent "
    "ranking within a few seconds of staleness, not instantly.",
    "Medium",
    ["eventual-consistency", "caching", "write-heavy"],
    reqs(peak_rps=15_000, read_ratio=0.6, p99_slo_ms=250, availability_slo=0.995, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Leaderboard API", replicas=2),
            node("cache", "cache", "Ranked Cache", hit_ratio=0.7),
            node("queue", "queue", "Score Update Queue"),
            node("worker", "worker", "Rank Recompute Worker"),
            node("db", "sql_primary", "Scores DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache", fraction=0.6),
            edge("cache", "db", fraction="miss"),
            edge("api", "queue", fraction=0.4, kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 4. availability_patterns ----------------------------------------------------
add_sim(
    "availability_patterns",
    "Design a Multi-Region Failover API",
    "Design an API that must keep serving reads even if an entire region's compute fails. Model the "
    "redundancy explicitly rather than assuming it away.",
    "Medium",
    ["redundancy", "failover", "spof"],
    reqs(peak_rps=10_000, read_ratio=0.85, p99_slo_ms=200, availability_slo=0.9995, growth_per_month=0.08),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Global Load Balancer"),
            node("api", "api_service", "API (single region)", replicas=1),
            node("db", "sql_primary", "Primary DB"),
            node("replica", "read_replica", "Standby Read Replica"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "db", fraction=0.7),
            edge("api", "replica", fraction=0.3),
            edge("db", "replica", kind="async"),
        ],
    ),
)

# 5. background_jobs -----------------------------------------------------------
add_sim(
    "background_jobs",
    "Design a Scheduled Report Generation Pipeline",
    "Design a system where users request a large report; generating it is too slow to do inline, so it has "
    "to run in the background while the user is told 'we'll notify you'.",
    "Easy",
    ["async", "queue", "worker-pool"],
    reqs(peak_rps=2_000, read_ratio=0.5, p99_slo_ms=500, availability_slo=0.99, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Report API", replicas=1),
            node("queue", "queue", "Report Job Queue"),
            node("worker", "worker", "Report Worker", replicas=2),
            node("db", "sql_primary", "Reports DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "queue", kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 7. cdn ------------------------------------------------------------------------
add_sim(
    "cdn",
    "Design a Static Asset Delivery Pipeline",
    "Design how images and static files are served to millions of users worldwide, most of whom request the "
    "same popular files repeatedly.",
    "Easy",
    ["cdn", "edge-caching", "read-heavy"],
    reqs(peak_rps=60_000, read_ratio=0.99, p99_slo_ms=100, availability_slo=0.9995, growth_per_month=0.12),
    graph(
        [
            node("client", "client", "Clients"),
            node("edge", "cache", "CDN Edge Cache", hit_ratio=0.92),
            node("api", "api_service", "Origin API", replicas=1),
            node("db", "sql_primary", "Asset Metadata DB"),
        ],
        [
            edge("client", "edge"),
            edge("edge", "api", fraction="miss"),
            edge("api", "db"),
        ],
    ),
)

# 8. load_balancing --------------------------------------------------------------
add_sim(
    "load_balancing",
    "Design a Horizontally Scaled API Gateway",
    "Design the entry point for a product with rapidly growing traffic. The gateway itself must never become "
    "the bottleneck, and the services behind it must scale out, not just up.",
    "Easy",
    ["load-balancing", "horizontal-scaling"],
    reqs(peak_rps=30_000, read_ratio=0.75, p99_slo_ms=200, availability_slo=0.999, growth_per_month=0.25),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "API Gateway LB"),
            node("api", "api_service", "API Service", replicas=3),
            node("db", "sql_primary", "Primary DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "db"),
        ],
    ),
)

# 9. application_layer ------------------------------------------------------------
add_sim(
    "application_layer",
    "Design a Microservices E-Commerce Checkout",
    "Design the checkout flow for an e-commerce site: validate the cart, reserve inventory, and hand off "
    "payment processing asynchronously so the user isn't stuck waiting on a card network.",
    "Hard",
    ["microservices", "async", "e-commerce"],
    reqs(peak_rps=8_000, read_ratio=0.5, p99_slo_ms=400, availability_slo=0.999, growth_per_month=0.15),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Checkout Service", replicas=2),
            node("cache", "cache", "Inventory Cache", hit_ratio=0.6),
            node("db", "sql_primary", "Orders DB"),
            node("queue", "queue", "Payment Queue"),
            node("worker", "worker", "Payment Worker", replicas=2),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache", fraction=0.5),
            edge("cache", "db", fraction="miss"),
            edge("api", "queue", fraction=0.5, kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 10. databases (x2) ----------------------------------------------------------------
add_sim(
    "databases",
    "Design a Product Catalog with Read Replicas",
    "Design a product catalog that is read constantly (browsing) and written rarely (restocking, price "
    "changes). Use read replicas to take load off the primary.",
    "Medium",
    ["read-replica", "read-heavy", "sql"],
    reqs(peak_rps=25_000, read_ratio=0.97, p99_slo_ms=200, availability_slo=0.999, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Catalog API", replicas=2),
            node("cache", "cache", "Catalog Cache", hit_ratio=0.8),
            node("db", "sql_primary", "Primary DB"),
            node("replica", "read_replica", "Read Replica", replicas=2),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache", fraction=0.8),
            edge("cache", "replica", fraction="miss"),
            edge("db", "replica", kind="async"),
            edge("api", "db", fraction=0.2),
        ],
    ),
)

add_sim(
    "databases",
    "Design a Key-Value Store Service",
    "Design a simple internal key-value service other teams will depend on: get/put by key, nothing fancier, "
    "but it needs to survive being hammered by many internal clients at once.",
    "Easy",
    ["key-value", "sql", "internal-service"],
    reqs(peak_rps=12_000, read_ratio=0.7, p99_slo_ms=100, availability_slo=0.999, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Internal Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "KV API", replicas=1),
            node("db", "sql_primary", "Storage Engine"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "db"),
        ],
    ),
)

# 11. caching (x2) --------------------------------------------------------------------
add_sim(
    "caching",
    "Design a Distributed Session Cache",
    "Design where user session data lives so that any API instance behind the load balancer can serve any "
    "user's requests without sticky sessions.",
    "Easy",
    ["caching", "sessions", "statelessness"],
    reqs(peak_rps=18_000, read_ratio=0.85, p99_slo_ms=150, availability_slo=0.999, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "API Service", replicas=2),
            node("cache", "cache", "Session Store", hit_ratio=0.9),
            node("db", "sql_primary", "Durable Session Backup"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache"),
            edge("cache", "db", fraction="miss"),
        ],
    ),
)

add_sim(
    "caching",
    "Design a Rate Limiter Backed by an In-Memory Store",
    "Design a rate limiter that every API request passes through. It must make an allow/deny decision in "
    "under a few milliseconds, at the full traffic volume of the product.",
    "Medium",
    ["rate-limiting", "caching", "high-throughput"],
    reqs(peak_rps=50_000, read_ratio=0.99, p99_slo_ms=50, availability_slo=0.999, growth_per_month=0.15),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "API + Limiter", replicas=2),
            node("cache", "cache", "Counter Store", hit_ratio=0.98),
            node("db", "sql_primary", "Policy DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache"),
            edge("cache", "db", fraction="miss"),
        ],
    ),
)

# 12. asynchronism ------------------------------------------------------------------
add_sim(
    "asynchronism",
    "Design a Video Transcoding Pipeline",
    "Design the backend for a video upload feature. Uploads must return quickly; the actual transcoding into "
    "multiple resolutions is slow and must happen off the request path.",
    "Medium",
    ["async", "queue", "media"],
    reqs(peak_rps=1_500, read_ratio=0.3, p99_slo_ms=600, availability_slo=0.99, growth_per_month=0.20),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Upload API", replicas=1),
            node("queue", "queue", "Transcode Queue"),
            node("worker", "worker", "Transcode Worker", replicas=2),
            node("db", "sql_primary", "Video Metadata DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "queue", kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 13. idempotency ---------------------------------------------------------------------
add_sim(
    "idempotency",
    "Design an Idempotent Payment Processing API",
    "Design a payment API where client retries (due to timeouts or network blips) must never charge a "
    "customer twice for the same logical request.",
    "Medium",
    ["idempotency", "payments", "retries"],
    reqs(peak_rps=5_000, read_ratio=0.2, p99_slo_ms=300, availability_slo=0.9995, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Payment API", replicas=2),
            node("cache", "cache", "Idempotency Key Store", hit_ratio=0.5),
            node("db", "sql_primary", "Ledger DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache"),
            edge("cache", "db", fraction="miss"),
        ],
    ),
)

# 14. communication ---------------------------------------------------------------------
add_sim(
    "communication",
    "Design a Real-Time Chat Backend",
    "Design the server side of a chat application: delivering messages between users with low latency, and "
    "persisting history so it survives a client reconnecting.",
    "Hard",
    ["real-time", "messaging", "queue"],
    reqs(peak_rps=20_000, read_ratio=0.5, p99_slo_ms=200, availability_slo=0.999, growth_per_month=0.15),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Chat Gateway", replicas=2),
            node("cache", "cache", "Presence Cache", hit_ratio=0.7),
            node("queue", "queue", "Message Queue"),
            node("worker", "worker", "Delivery Worker", replicas=2),
            node("db", "sql_primary", "Message History DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "cache", fraction=0.3),
            edge("cache", "db", fraction="miss"),
            edge("api", "queue", fraction=0.7, kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 15. performance_antipatterns -----------------------------------------------------------
add_sim(
    "performance_antipatterns",
    "Diagnose and Fix an Overloaded Checkout Service",
    "This checkout service was built for a demo and is now in production. It is deliberately under-sized: "
    "find out why it falls over under real load and redesign it. There is no 'correct' starting diagram here, "
    "only this broken one to fix.",
    "Medium",
    ["antipattern", "capacity-planning", "redesign"],
    reqs(peak_rps=15_000, read_ratio=0.6, p99_slo_ms=250, availability_slo=0.999, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Checkout API", replicas=1),
            node("db", "sql_primary", "Orders DB", replicas=1),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "db"),
        ],
    ),
)

# 16. cloud_patterns ------------------------------------------------------------------------
add_sim(
    "cloud_patterns",
    "Design a CQRS-based Order Management System",
    "Design an order management system where writes (placing orders) and reads (order history, dashboards) "
    "have very different load shapes, and you want to scale and optimise them independently.",
    "Hard",
    ["cqrs", "read-write-split"],
    reqs(peak_rps=10_000, read_ratio=0.7, p99_slo_ms=300, availability_slo=0.999, growth_per_month=0.12),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("write_api", "api_service", "Command API", replicas=1),
            node("queue", "queue", "Order Events Queue"),
            node("worker", "worker", "Projection Worker", replicas=1),
            node("db", "sql_primary", "Write DB (orders)"),
            node("read_api", "api_service", "Query API", replicas=2),
            node("cache", "cache", "Read Model Cache", hit_ratio=0.75),
            node("replica", "read_replica", "Read Model Store"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "write_api", fraction=0.3),
            edge("write_api", "queue", kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
            edge("lb", "read_api", fraction=0.7),
            edge("read_api", "cache"),
            edge("cache", "replica", fraction="miss"),
            edge("db", "replica", kind="async"),
        ],
    ),
)

# 17. reliability (x2) ---------------------------------------------------------------------------
add_sim(
    "reliability",
    "Design a Circuit-Breaker Protected Payment Gateway",
    "Design an API that calls a slow, occasionally-overloaded downstream payment partner, without letting "
    "that partner's slowness cascade into your own service falling over.",
    "Medium",
    ["circuit-breaker", "cascading-failure"],
    reqs(peak_rps=6_000, read_ratio=0.3, p99_slo_ms=400, availability_slo=0.999, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Payment Gateway", replicas=2),
            node("partner", "api_service", "Downstream Partner (slow)", replicas=1, mu=150, base_latency_ms=40),
            node("db", "sql_primary", "Transactions DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "partner"),
            edge("api", "db"),
        ],
    ),
)

add_sim(
    "reliability",
    "Design a Bulkhead-Isolated Notification Service",
    "Design a notification service sending email, SMS and push. One noisy, slow channel should never be able "
    "to starve the others of worker capacity.",
    "Medium",
    ["bulkhead", "isolation", "worker-pool"],
    reqs(peak_rps=9_000, read_ratio=0.1, p99_slo_ms=500, availability_slo=0.995, growth_per_month=0.10),
    graph(
        [
            node("client", "client", "Clients"),
            node("lb", "load_balancer", "Load Balancer"),
            node("api", "api_service", "Notification API", replicas=1),
            node("queue", "queue", "Notification Queue"),
            node("worker", "worker", "Notification Worker Pool", replicas=3),
            node("db", "sql_primary", "Delivery Log DB"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "queue", kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

# 18. monitoring --------------------------------------------------------------------------------
add_sim(
    "monitoring",
    "Design a Metrics Ingestion Pipeline",
    "Design the pipeline that ingests a metric data point from every service, every few seconds, across an "
    "entire company's infrastructure, and makes it queryable on a dashboard within a minute.",
    "Medium",
    ["observability", "high-throughput", "time-series"],
    reqs(peak_rps=35_000, read_ratio=0.2, p99_slo_ms=300, availability_slo=0.995, growth_per_month=0.15),
    graph(
        [
            node("client", "client", "Metric Producers"),
            node("lb", "load_balancer", "Ingestion LB"),
            node("api", "api_service", "Ingestion API", replicas=2),
            node("queue", "queue", "Metrics Queue"),
            node("worker", "worker", "Aggregation Worker", replicas=2),
            node("db", "sql_primary", "Time-Series Store"),
        ],
        [
            edge("client", "lb"),
            edge("lb", "api"),
            edge("api", "queue", kind="async"),
            edge("queue", "worker", kind="async"),
            edge("worker", "db"),
        ],
    ),
)

assert len(SIMULATABLE) == 20, f"Expected 20 simulatable prompts, got {len(SIMULATABLE)}"


# --------------------------------------------------------------------------
# Lightweight (non-simulatable) cards: authored per subtopic.
# Each tuple: (title, scenario, difficulty, tags)
# --------------------------------------------------------------------------

LIGHTWEIGHT: dict[str, list[tuple[str, str, str, list[str]]]] = {
    "basics": [
        ("Design a Pastebin", "A service for sharing text snippets with a generated link, optional expiry.", "Easy", ["read-heavy", "storage"]),
        ("Design a Tiny URL Analytics Dashboard", "Extend a URL shortener with per-link click counts and referrer tracking.", "Easy", ["analytics", "write-path"]),
        ("Design a Parking Lot System", "Model floors, spot types, entry/exit, and pricing for a multi-level garage.", "Easy", ["oop-design", "state-machine"]),
        ("Design a Vending Machine", "Model inventory, payment, and dispensing as a state machine.", "Easy", ["oop-design", "state-machine"]),
        ("Design a Tic-Tac-Toe Game Server", "Two players, turn validation, win detection, as a backend service.", "Easy", ["state-machine", "oop-design"]),
        ("Design an Elevator System", "Multiple elevators, multiple floors, request scheduling and dispatch.", "Medium", ["scheduling", "oop-design"]),
        ("Approach: Estimate Back-of-the-Envelope Capacity", "Given a product description, estimate QPS, storage, and bandwidth from first principles.", "Easy", ["estimation"]),
        ("Approach: Choosing Between SQL and NoSQL", "Given access patterns, justify a database family choice with trade-offs.", "Easy", ["databases", "trade-offs"]),
        ("Design a Library Management System", "Books, members, checkouts, holds, and late fees.", "Easy", ["oop-design", "crud"]),
    ],
    "scaling": [
        ("Design Instagram", "Photo sharing, follows, and a home feed at hundreds of millions of users.", "Hard", ["fan-out", "media-storage"]),
        ("Design Twitter", "Short posts, follows, retweets, and a feed with celebrity fan-out problems.", "Hard", ["fan-out", "celebrity-problem"]),
        ("Design YouTube", "Video upload, transcoding, and globally distributed playback.", "Hard", ["media", "cdn"]),
        ("Design a Ride-Sharing Dispatch System", "Match riders to nearby drivers in real time across a whole city.", "Hard", ["geospatial", "real-time"]),
        ("Design an Ad Click Aggregation System", "Ingest and aggregate billions of ad click events per day.", "Hard", ["big-data", "aggregation"]),
        ("Design a Search Autocomplete Service", "Suggest completions as a user types, at very low latency and huge QPS.", "Medium", ["trie", "caching"]),
        ("Design a Web Crawler", "Crawl the web at scale while respecting robots.txt and avoiding duplicate work.", "Hard", ["distributed-systems", "dedup"]),
        ("Design a Distributed File Storage System (Dropbox-like)", "Sync files across devices with conflict resolution and deduplication.", "Hard", ["sync", "storage"]),
        ("Scale a Single-Server App to Multi-Region", "Walk through the stages of scaling a monolith to a global, multi-region deployment.", "Medium", ["growth-path"]),
    ],
    "consistency_patterns": [
        ("Design a Shopping Cart with Strong Consistency on Checkout", "Cart updates can be loose, but checkout inventory decrement must be exact.", "Medium", ["strong-consistency", "inventory"]),
        ("Design a Collaborative Document Editor", "Multiple users edit the same document; reconcile concurrent edits.", "Hard", ["crdt", "operational-transform"]),
        ("Design a Distributed Counter Service", "A like/view counter that must stay approximately correct under massive concurrent writes.", "Medium", ["counters", "approximate-consistency"]),
        ("Explain Read-Your-Writes Consistency for a Profile Edit", "A user edits their profile and immediately reloads the page; what guarantees are needed?", "Easy", ["session-consistency"]),
        ("Design a Distributed Lock Service", "Coordinate exclusive access to a resource across multiple nodes.", "Hard", ["distributed-locks", "coordination"]),
        ("Design a Bank Account Ledger", "Transfers between accounts must never lose or duplicate money under concurrent requests.", "Hard", ["acid", "financial-consistency"]),
        ("Design an Inventory Service for Flash Sales", "Thousands of concurrent buyers for limited stock; avoid overselling.", "Hard", ["oversell-prevention", "locking"]),
        ("Compare Strong vs Eventual Consistency for a Comments Feature", "When is it acceptable for a new comment to be briefly invisible to some readers?", "Easy", ["trade-offs"]),
        ("Design a Multi-Region Database Replication Strategy", "Choose and justify a consistency model for a globally replicated dataset.", "Hard", ["replication", "multi-region"]),
    ],
    "availability_patterns": [
        ("Design a Health-Check and Auto-Healing System", "Detect unhealthy instances and replace them automatically.", "Medium", ["health-checks", "self-healing"]),
        ("Design an Active-Active Multi-Region Deployment", "Serve traffic from two regions simultaneously with data synced between them.", "Hard", ["multi-region", "active-active"]),
        ("Design a Graceful Degradation Strategy for a Product Page", "Decide what to show when the recommendations service is down but the page must still load.", "Medium", ["graceful-degradation"]),
        ("Design a Disaster Recovery Plan for a Payments Database", "Define RPO/RTO and the failover mechanism for a critical datastore.", "Hard", ["disaster-recovery", "rpo-rto"]),
        ("Design a Leader Election Mechanism for a Cluster", "Ensure exactly one node acts as leader, with automatic failover if it dies.", "Hard", ["leader-election", "consensus"]),
        ("Design a Blue-Green Deployment Pipeline", "Deploy new versions with zero downtime and instant rollback.", "Medium", ["deployment", "zero-downtime"]),
        ("Design a Read-Path Fallback When the Cache Cluster Is Down", "The cache is unavailable; the database alone cannot take full load. What do you do?", "Medium", ["fallback", "overload-protection"]),
        ("Design a Standby Database Promotion Workflow", "Automate promoting a replica to primary when the primary fails.", "Medium", ["failover", "replication"]),
        ("Design Chaos Testing for a Payment System", "Deliberately inject failures in production-like environments to validate resilience.", "Medium", ["chaos-engineering"]),
    ],
    "background_jobs": [
        ("Design a Daily Email Digest System", "Send a personalized summary email to millions of users at a scheduled time.", "Medium", ["scheduling", "batch"]),
        ("Design a Cron-Based Task Scheduler Service", "A shared service other teams submit scheduled jobs to.", "Medium", ["scheduling", "distributed-cron"]),
        ("Design a Data Export Feature", "A user requests an export of all their data; generate and deliver it asynchronously.", "Easy", ["async", "gdpr"]),
        ("Design a Retry Strategy for Failed Background Jobs", "Jobs fail transiently; design backoff, retry limits, and dead-letter handling.", "Medium", ["retries", "dlq"]),
        ("Design a Billing Invoice Generation Pipeline", "Generate and send invoices to all customers at the end of each billing cycle.", "Medium", ["batch", "billing"]),
        ("Design a Search Index Rebuild Job", "Periodically rebuild a search index from the source of truth without downtime.", "Hard", ["indexing", "zero-downtime"]),
        ("Design a Job Priority Queue", "Some background jobs are urgent (password reset emails), others are not (weekly digests).", "Medium", ["prioritization"]),
        ("Design a Distributed Cron Service Avoiding Duplicate Runs", "Ensure a scheduled job runs exactly once even with multiple scheduler instances.", "Hard", ["idempotency", "distributed-cron"]),
        ("Design a Media Thumbnail Generation Pipeline", "Generate multiple thumbnail sizes for every uploaded image, asynchronously.", "Easy", ["async", "media"]),
    ],
    "dns": [
        ("Explain How a Domain Resolves to an IP End-to-End", "Walk through resolver, root, TLD, and authoritative name servers for a cold lookup.", "Easy", ["dns-resolution"]),
        ("Design a GeoDNS-Based Traffic Routing Strategy", "Route users to the nearest healthy region using DNS.", "Medium", ["geodns", "routing"]),
        ("Explain DNS-Based Load Balancing vs a Hardware Load Balancer", "Compare trade-offs for distributing traffic across servers.", "Easy", ["load-balancing", "trade-offs"]),
        ("Design a DNS Failover Strategy for a Multi-Region Service", "Automatically stop routing to a region failing health checks.", "Medium", ["failover", "health-checks"]),
        ("Explain the Effect of TTL on a DNS-Based Deployment Cutover", "How does the chosen DNS TTL affect how fast a migration can be rolled back?", "Easy", ["ttl", "migration"]),
        ("Design a Split-Horizon DNS Setup for Internal vs External Traffic", "Internal services should resolve differently than public clients.", "Medium", ["split-horizon"]),
        ("Explain Anycast DNS and Why CDNs Use It", "How does routing the same IP from many locations improve latency and resilience?", "Medium", ["anycast", "cdn"]),
        ("Design a Service Discovery Mechanism Using DNS", "Internal microservices need to find each other's current instances.", "Medium", ["service-discovery"]),
        ("Diagnose a DNS Propagation Delay Incident", "A DNS record was changed but some users still hit the old server. Why, and what would you check?", "Easy", ["troubleshooting"]),
        ("Design a Rate-Limited Public DNS Resolver", "Prevent a public-facing recursive resolver from being used for DDoS amplification.", "Hard", ["security", "abuse-prevention"]),
    ],
    "cdn": [
        ("Design Image Delivery for a Social Media App", "Serve resized, compressed images quickly to users worldwide.", "Medium", ["media", "edge-caching"]),
        ("Design Cache Invalidation for a CDN-Fronted API", "A backend value changes; purge or update the CDN's cached copy correctly.", "Hard", ["cache-invalidation"]),
        ("Choose Between Push CDN and Pull CDN for a Video Platform", "Trade-offs for origin load, freshness, and storage cost.", "Easy", ["push-vs-pull"]),
        ("Design Edge Compute for A/B Testing at the CDN Layer", "Run experiment bucketing logic at the edge, before hitting origin.", "Medium", ["edge-compute"]),
        ("Design a Signed URL Scheme for Private CDN Content", "Serve paid video content through a CDN without letting it be freely redistributed.", "Medium", ["security", "signed-urls"]),
        ("Design Origin Shield to Protect a Backend from Cache Misses", "Prevent a cold cache from causing a thundering herd on the origin.", "Medium", ["origin-shield", "stampede"]),
        ("Design Multi-CDN Failover for a High-Traffic Site", "Avoid a single CDN provider outage taking the whole site down.", "Hard", ["multi-cdn", "failover"]),
        ("Explain Cache-Control Headers for a Mixed Static/Dynamic Site", "Decide caching policy per content type (HTML, JS bundle, user avatar).", "Easy", ["http-caching"]),
        ("Design Live Video Streaming Delivery via CDN", "Distribute a live stream to millions of concurrent viewers with low latency.", "Hard", ["live-streaming"]),
    ],
    "load_balancing": [
        ("Compare Layer 4 vs Layer 7 Load Balancing", "Trade-offs for a service that needs content-based routing vs raw throughput.", "Easy", ["l4-vs-l7"]),
        ("Design Consistent Hashing for a Sharded Cache Cluster", "Add/remove cache nodes without invalidating most of the cache.", "Hard", ["consistent-hashing"]),
        ("Design Load Balancing for Long-Lived WebSocket Connections", "Standard round robin doesn't work well for sticky, long-lived connections.", "Medium", ["websockets", "sticky-sessions"]),
        ("Design a Weighted Load Balancing Strategy for Canary Releases", "Send 5% of traffic to a new version before a full rollout.", "Medium", ["canary", "weighted-routing"]),
        ("Design Load Balancer Health Checks for a Rolling Deployment", "Avoid routing traffic to instances that are still starting up.", "Easy", ["health-checks", "deployment"]),
        ("Design Global Server Load Balancing Across Regions", "Route users to the best region based on latency and capacity.", "Hard", ["gslb", "multi-region"]),
        ("Design a Load Balancer for a gRPC Service", "HTTP/2 multiplexed connections behave differently than plain HTTP/1.1 for load balancing.", "Medium", ["grpc", "http2"]),
        ("Explain Least-Connections vs Round-Robin Balancing", "When does tracking active connections beat simple rotation?", "Easy", ["algorithms"]),
        ("Design Load Shedding for an Overloaded API", "When the system is past capacity, decide which requests to reject first.", "Medium", ["load-shedding", "overload"]),
    ],
    "application_layer": [
        ("Design a Monolith-to-Microservices Migration Plan", "Incrementally split a monolith without a risky big-bang rewrite.", "Hard", ["migration", "strangler-fig"]),
        ("Design an API Gateway for 50 Microservices", "Centralize auth, rate limiting, and routing for many backend services.", "Medium", ["api-gateway"]),
        ("Design Service-to-Service Authentication in a Microservices Mesh", "Services must verify each other's identity, not just the end user's.", "Medium", ["mtls", "service-mesh"]),
        ("Design a Backend-for-Frontend (BFF) for Mobile vs Web", "Different clients need different shapes of the same underlying data.", "Medium", ["bff"]),
        ("Design Service Discovery for Dynamically Scaling Containers", "Instances come and go; callers need to always find a live one.", "Medium", ["service-discovery"]),
        ("Design a Saga Pattern for a Multi-Service Order Workflow", "An order touches inventory, payment, and shipping services; handle partial failure.", "Hard", ["saga", "distributed-transactions"]),
        ("Design an Event-Driven Architecture for an Order System", "Services react to events rather than calling each other directly.", "Hard", ["event-driven"]),
        ("Design a Feature Flag System for Gradual Rollouts", "Turn features on for specific user segments without a redeploy.", "Medium", ["feature-flags"]),
        ("Design a GraphQL Gateway Over Existing REST Microservices", "Let clients query multiple services in one request without over-fetching.", "Medium", ["graphql"]),
    ],
    "databases": [
        ("Choose a Sharding Key for a Multi-Tenant SaaS Database", "Pick a shard key that avoids hot shards across very different tenant sizes.", "Hard", ["sharding"]),
        ("Design Schema Migration for a Zero-Downtime Deployment", "Change a production table's schema without taking the service down.", "Medium", ["migrations"]),
        ("Compare Document, Column-Family, and Graph Databases for a Social Network", "Pick a data model to match friend-of-friend and content-feed queries.", "Medium", ["nosql", "data-modeling"]),
        ("Design a Time-Series Database Schema for IoT Sensor Data", "Millions of sensors reporting every few seconds; design for write throughput and range queries.", "Hard", ["time-series", "iot"]),
        ("Design Database Connection Pooling for a High-Concurrency Service", "Many app instances must share a limited number of database connections efficiently.", "Easy", ["connection-pooling"]),
        ("Design a Search Index Alongside a Primary Database", "Full-text search doesn't fit well in a relational index; keep a search engine in sync.", "Medium", ["search", "dual-write"]),
        ("Design Database Partitioning for a Multi-Year Transaction Log", "Old data is rarely queried; keep it cheap to store without slowing down recent queries.", "Medium", ["partitioning"]),
        ("Design a Write-Ahead Log Based Durability Strategy", "Explain how a database guarantees committed writes survive a crash.", "Medium", ["wal", "durability"]),
    ],
    "caching": [
        ("Design Cache-Aside vs Write-Through for a User Profile Service", "Compare consistency and complexity trade-offs for two caching strategies.", "Easy", ["cache-patterns"]),
        ("Design Cache Invalidation for a Multi-Service Architecture", "A value changes in one service; every cache that holds it must be updated or expired.", "Hard", ["invalidation"]),
        ("Design a Cache Warming Strategy After a Deployment", "Avoid a flood of cache misses right after restarting cache nodes.", "Medium", ["cache-warming"]),
        ("Design Protection Against Cache Stampede for a Popular Key", "Many requests miss the same expiring key simultaneously and hammer the database.", "Medium", ["stampede", "locking"]),
        ("Design a Multi-Layer Caching Strategy (Browser, CDN, App, DB)", "Decide what to cache at each layer and for how long.", "Medium", ["layered-caching"]),
        ("Design an LRU Cache as a Standalone Component", "Implement eviction policy and complexity trade-offs for a bounded-size cache.", "Easy", ["eviction-policy"]),
        ("Design Write-Behind Caching for a High-Write Analytics Counter", "Batch writes through the cache to the database to absorb a write-heavy workload.", "Medium", ["write-behind"]),
        ("Design Cache Partitioning Across Multiple Redis Clusters", "A single cache node can't hold the whole working set; split it without hotspotting.", "Hard", ["cache-sharding"]),
    ],
    "asynchronism": [
        ("Design an Event Bus for Order and Inventory Updates", "Decouple order processing from inventory, shipping, and analytics consumers.", "Medium", ["event-bus", "pub-sub"]),
        ("Design At-Least-Once vs Exactly-Once Message Processing", "Compare the guarantees and the application-level work each requires.", "Hard", ["delivery-guarantees"]),
        ("Design a Dead-Letter Queue Strategy for Poison Messages", "A malformed message keeps failing processing; prevent it from blocking the queue.", "Medium", ["dlq"]),
        ("Design Backpressure Handling for a Slow Downstream Consumer", "Producers outpace consumers; decide how to avoid unbounded queue growth.", "Medium", ["backpressure"]),
        ("Design a Pub-Sub System for Live Sports Score Updates", "Push updates to many subscribed clients with low latency.", "Medium", ["pub-sub", "real-time"]),
        ("Design Ordered Message Processing Per User in a Shared Queue", "Guarantee per-user ordering while still processing different users in parallel.", "Hard", ["ordering", "partitioning"]),
        ("Design Async Email Sending with Delivery Confirmation Tracking", "Decouple sending from the request path while tracking bounces and opens.", "Easy", ["async", "email"]),
        ("Design a Webhook Delivery System with Retries", "Reliably deliver events to third-party endpoints that may be slow or down.", "Medium", ["webhooks", "retries"]),
        ("Design Event Sourcing for an Account Balance System", "Store state as a sequence of events rather than overwriting a single row.", "Hard", ["event-sourcing"]),
    ],
    "idempotency": [
        ("Design Idempotency Keys for a Public REST API", "Let clients safely retry POST requests without server-side duplication.", "Medium", ["idempotency-key"]),
        ("Design Idempotent Message Consumers for an Event-Driven System", "A consumer may receive the same event twice; processing must be safe either way.", "Medium", ["event-driven"]),
        ("Design an Exactly-Once Email Send Guarantee", "Ensure a triggered email (e.g. 'your order shipped') is never sent twice.", "Medium", ["notifications"]),
        ("Design Idempotent Database Migrations", "A migration script might be re-run accidentally; it must not corrupt data if it is.", "Easy", ["migrations"]),
        ("Design an Idempotent File Upload Resume Mechanism", "A large upload is interrupted and resumed; avoid duplicate or corrupted chunks.", "Medium", ["uploads", "resumability"]),
        ("Design Idempotency for a Distributed Booking System", "Two retried requests for the same seat booking must not both succeed.", "Hard", ["booking", "concurrency"]),
        ("Explain Why GET Should Be Idempotent but POST Is Not by Default", "Connect HTTP method semantics to retry-safety for clients and proxies.", "Easy", ["http-semantics"]),
        ("Design Idempotent Batch Job Reprocessing", "A nightly batch job fails partway through; rerunning it must not double-process completed records.", "Medium", ["batch-processing"]),
        ("Design a De-duplication Layer for an Analytics Ingestion Pipeline", "The same event may arrive more than once from unreliable client SDKs.", "Medium", ["deduplication", "analytics"]),
    ],
    "communication": [
        ("Compare REST, GraphQL, and gRPC for a Mobile App Backend", "Pick a protocol given mobile bandwidth and battery constraints.", "Easy", ["protocols", "trade-offs"]),
        ("Design Long Polling vs WebSockets for Live Notifications", "Compare resource usage and latency for keeping a client updated.", "Medium", ["real-time", "trade-offs"]),
        ("Design a Bi-Directional Streaming API with gRPC", "Both client and server need to push updates continuously over one connection.", "Hard", ["grpc", "streaming"]),
        ("Design Server-Sent Events for a Live Dashboard", "Push metric updates to a browser without full WebSocket complexity.", "Easy", ["sse"]),
        ("Design a Request/Response Protocol Resilient to Mobile Network Drops", "Mobile clients lose connectivity frequently; design for graceful recovery.", "Medium", ["mobile", "resilience"]),
        ("Design API Versioning for a Public API Used by Third Parties", "Evolve the API without breaking existing integrations.", "Medium", ["api-versioning"]),
        ("Design a Protocol for IoT Devices with Intermittent Connectivity", "Devices on cellular/LoRa connect briefly and infrequently; design the sync protocol.", "Hard", ["iot", "intermittent-connectivity"]),
        ("Design Pagination for a Large Public API", "Compare offset-based and cursor-based pagination for a feed endpoint.", "Easy", ["pagination"]),
        ("Design Request Compression and Batching for a Chatty Mobile Client", "Reduce the number of round trips and bytes for a bandwidth-constrained app.", "Medium", ["batching", "compression"]),
    ],
    "performance_antipatterns": [
        ("Diagnose an N+1 Query Problem in an Order List Endpoint", "An endpoint that lists orders is making one extra query per order. Find it and fix it.", "Easy", ["n-plus-one"]),
        ("Diagnose a Service Degrading Under a 'Thundering Herd' After a Cache Expiry", "Every client refreshes at once right after a popular cache key expires.", "Medium", ["thundering-herd"]),
        ("Diagnose a Chatty Microservice Making 20 Calls Per Request", "A single user action fans out into far too many synchronous downstream calls.", "Medium", ["chattiness"]),
        ("Diagnose Unbounded Memory Growth in a Request-Handling Service", "A service's memory climbs steadily under sustained load until it crashes.", "Hard", ["memory-leak"]),
        ("Diagnose a Synchronous Call Chain Causing Cascading Timeouts", "One slow downstream call is making every upstream caller time out in sequence.", "Medium", ["cascading-failure"]),
        ("Diagnose Excessive Lock Contention in a High-Concurrency Counter", "A shared counter under high write concurrency has collapsed in throughput.", "Hard", ["lock-contention"]),
        ("Diagnose a Database Connection Pool Exhaustion Incident", "The app suddenly can't get a DB connection under moderate load; find the leak.", "Medium", ["connection-pooling"]),
        ("Diagnose a Full Table Scan Hiding Behind a Slow 'Simple' Query", "A query that looks trivial is actually scanning millions of rows.", "Easy", ["query-planning"]),
        ("Diagnose a Service Spending Most of Its Time on Serialization", "Profiling shows most CPU time goes to JSON encoding/decoding, not business logic.", "Medium", ["serialization-overhead"]),
    ],
    "cloud_patterns": [
        ("Design the Strangler Fig Pattern for a Legacy System Migration", "Incrementally replace a legacy system behind a stable interface.", "Medium", ["strangler-fig", "migration"]),
        ("Design a Sidecar Pattern for Cross-Cutting Concerns", "Add logging, metrics, and mTLS to services without modifying their code.", "Medium", ["sidecar", "service-mesh"]),
        ("Design a Circuit Breaker as a Reusable Cloud Pattern", "Generalize failure isolation into a pattern usable across many services.", "Medium", ["circuit-breaker"]),
        ("Design the Gateway Aggregation Pattern for a Mobile Client", "Combine several backend calls into one client-facing request.", "Medium", ["gateway-aggregation"]),
        ("Design a Queue-Based Load Leveling Pattern for Bursty Traffic", "Smooth out traffic spikes by buffering work in a queue rather than scaling instantly.", "Medium", ["load-leveling"]),
        ("Design the Anti-Corruption Layer Pattern Between Old and New Systems", "Translate between a legacy system's model and a new system's model during migration.", "Medium", ["anti-corruption-layer"]),
        ("Design a Compute Resource Consolidation Strategy for Low-Traffic Services", "Many small, low-traffic services are wasting dedicated resources; consolidate them.", "Easy", ["resource-consolidation"]),
        ("Design the Backends-for-Frontends Pattern for Web, iOS, and Android", "Each client type gets a tailored API layer instead of one generic backend.", "Medium", ["bff"]),
        ("Design a Static Content Hosting Pattern for a Single-Page App", "Separate static asset hosting from dynamic API serving for cost and scale.", "Easy", ["static-hosting"]),
    ],
    "reliability": [
        ("Design a Retry Strategy with Exponential Backoff and Jitter", "Avoid synchronized retry storms from many clients after a transient failure.", "Easy", ["retries", "backoff"]),
        ("Design a Timeout Strategy Across a Multi-Hop Service Call Chain", "Each hop needs its own budget so the whole chain doesn't exceed the user's patience.", "Medium", ["timeouts"]),
        ("Design a Blast-Radius-Limiting Deployment Strategy", "Roll out changes to a small percentage of traffic/instances first.", "Medium", ["canary", "blast-radius"]),
        ("Design Graceful Shutdown for a Service Behind a Load Balancer", "Stop sending new requests to an instance before it terminates in-flight ones.", "Easy", ["graceful-shutdown"]),
        ("Design a Rate Limiter to Protect a Backend from a Buggy Client", "One misbehaving client is hammering the API; protect the service without blocking everyone.", "Medium", ["rate-limiting", "abuse-protection"]),
        ("Design a Redundant Message Delivery System for Critical Alerts", "A critical alert must reach an on-call engineer even if one delivery channel fails.", "Medium", ["redundancy", "alerting"]),
        ("Design a Capacity Planning Process for Seasonal Traffic Spikes", "Prepare infrastructure for predictable but extreme spikes (e.g. a sale event).", "Medium", ["capacity-planning"]),
        ("Design Health Endpoint Monitoring for a Fleet of Services", "Standardize how every service reports liveness and readiness.", "Easy", ["health-checks"]),
    ],
    "monitoring": [
        ("Design a Distributed Tracing System Across Microservices", "Follow a single request as it crosses many services, with timing per hop.", "Hard", ["distributed-tracing"]),
        ("Design an Alerting System That Avoids Alert Fatigue", "Too many low-signal alerts are causing engineers to ignore pages. Fix the signal-to-noise ratio.", "Medium", ["alerting", "alert-fatigue"]),
        ("Design a Log Aggregation Pipeline for Hundreds of Services", "Centralize logs from everywhere so they're searchable within seconds of being written.", "Medium", ["log-aggregation"]),
        ("Design an SLO/SLA Tracking Dashboard for a Platform Team", "Track error budgets per service against agreed service-level objectives.", "Medium", ["slo", "error-budget"]),
        ("Design Anomaly Detection for a Key Business Metric", "Automatically flag when signups or revenue deviate unusually from the normal pattern.", "Hard", ["anomaly-detection"]),
        ("Design a Synthetic Monitoring System for Critical User Flows", "Continuously simulate real user journeys (login, checkout) to catch issues before users do.", "Medium", ["synthetic-monitoring"]),
        ("Design Real-User Monitoring for Frontend Performance", "Measure actual page-load and interaction latency experienced by real users.", "Medium", ["rum", "frontend-performance"]),
        ("Design a Centralized Dashboard for On-Call Engineers", "One place showing system health, recent deploys, and active incidents.", "Easy", ["observability", "on-call"]),
        ("Design Audit Logging for a Multi-Tenant SaaS Platform", "Every sensitive action must be attributable and tamper-evident, per tenant.", "Medium", ["audit-logging", "compliance"]),
    ],
}


def build():
    prompts = []
    counters = {sid: 0 for sid, _ in SUBTOPICS}

    def add(subtopic_id, title, scenario, difficulty, tags, simulatable, requirements=None, starter_graph=None):
        counters[subtopic_id] += 1
        prompts.append(
            {
                "id": f"sd.{subtopic_id}.p{counters[subtopic_id]:02d}",
                "subtopic_id": subtopic_id,
                "subtopic_name": SUBTOPIC_NAME[subtopic_id],
                "title": title,
                "scenario": scenario,
                "difficulty": difficulty,
                "tags": tags,
                "simulatable": simulatable,
                "requirements": requirements,
                "starter_graph": starter_graph,
            }
        )

    for sim in SIMULATABLE:
        add(
            sim["subtopic_id"], sim["title"], sim["scenario"], sim["difficulty"], sim["tags"],
            True, sim["requirements"], sim["starter_graph"],
        )

    for subtopic_id, items in LIGHTWEIGHT.items():
        for title, scenario, difficulty, tags in items:
            add(subtopic_id, title, scenario, difficulty, tags, False)

    for subtopic_id, count in counters.items():
        if count != 10:
            raise AssertionError(f"Subtopic '{subtopic_id}' has {count} prompts, expected 10.")

    return prompts


def main():
    prompts = build()
    out = {
        "subtopics": [{"id": sid, "name": name} for sid, name in SUBTOPICS],
        "total_prompts": len(prompts),
        "simulatable_count": sum(1 for p in prompts if p["simulatable"]),
        "prompts": prompts,
    }

    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {len(prompts)} prompts ({out['simulatable_count']} simulatable) to {OUT_PATH}")


if __name__ == "__main__":
    main()

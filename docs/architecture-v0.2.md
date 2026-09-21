# News Center V0.2 Architecture

## 1. Goal

V0.2 evolves News Center from a ZAKER-specific crawler service into a provider-independent News Content Hub while preserving the existing public API.

The core dependency direction is:

```text
API / Scheduler
      |
      v
IngestionService
      |
      +----------------+
      |                |
      v                v
NewsProvider       NewsRepository
      |                |
      v                v
ZakerProvider       SQLite
```

The service remains responsible for acquisition, normalization, validation, deduplication, persistence and retrieval. LLM rewriting, summarization for personas, recommendation and TTS remain outside this service.

## 2. Layer boundaries

### domain

`app/domain/models.py`

Defines provider-independent domain objects.

Current primary model:

- `ArticleCandidate`
- `TopicIngestionResult`
- `IngestionResult`

`ArticleCandidate.tag` is temporarily retained as a compatibility alias for `topic` because the V0.1 SQLite table still stores a single `tag`.

### providers

`app/providers/`

Defines source adapters.

- `NewsProvider`: provider contract
- `ProviderRegistry`: runtime registry
- `ZakerProvider`: adapter around the existing ZAKER crawler

Routes and scheduler code must not call `fetch_zaker()` directly after this migration.

Adding a new source should normally require only:

1. implementing a provider,
2. registering it,
3. mapping its raw response to `ArticleCandidate`.

### services

`app/services/ingestion.py`

`IngestionService` coordinates:

1. topic normalization,
2. bounded concurrent provider fetching,
3. persistence,
4. per-topic statistics,
5. partial/failure status aggregation.

It also serializes full ingestion runs with an async lock so manual and scheduled full runs do not overlap inside one process.

### repositories

`app/repositories/`

Repository interfaces isolate persistence from application services.

V0.2 initially wraps the existing SQLite database functions. A future schema migration must stay behind this boundary so providers and services do not need to change.

## 3. V0.2 compatibility strategy

The first V0.2 foundation intentionally does not migrate the public schema.

Existing endpoints remain:

- `GET /topics`
- `GET /news`
- `GET /news/{id}`
- `POST /fetch`
- `GET /scheduler/status`
- `POST /scheduler/config`
- `POST /scheduler/run`

The legacy `app/crawler/zaker.py` remains operational and is wrapped by `ZakerProvider`.

The existing `news` table also remains operational during this phase.

## 4. Persistence improvement in this phase

`insert_news_batch()` now writes a batch using a single SQLite connection and transaction rather than opening and committing one transaction per article.

This is deliberately implemented before larger schema changes because it improves ingestion efficiency without changing the API or stored data shape.

## 5. Scheduler behavior

The scheduler engine and the enabled state of the fetch job are treated separately.

When an API request enables or resumes scheduling while the in-process scheduler engine has not started yet, the scheduler starts first and then applies the job state. This prevents persisted configuration from saying `enabled=true` while no scheduler engine is running.

## 6. Next schema migration

The next phase should replace the single-topic `news` model with:

```text
articles
  id
  provider
  source_article_id
  canonical_url
  title
  source
  summary
  content
  image_url
  language
  published_at
  fetched_at
  updated_at
  content_hash

article_topics
  article_id
  topic
```

This solves the current limitation where one URL can only retain one topic.

Migration rules:

- keep repository interfaces stable,
- introduce canonical URL normalization,
- introduce content/title fingerprinting,
- migrate old `news.tag` rows into `article_topics`,
- keep API compatibility during the transition.

## 7. Later phases

After the Article/Topics migration:

1. SQLite FTS5 search
2. canonical URL + content hash deduplication
3. richer article content and image metadata
4. admin authentication for mutation endpoints
5. health/readiness/metrics
6. optional external scheduler/database only when deployment scale requires it

PostgreSQL, Redis, Celery and Elasticsearch are intentionally not required for V0.2.

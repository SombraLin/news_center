# News Center V0.2 Architecture

## 1. Goal

V0.2 evolves News Center from a ZAKER-specific crawler service into a provider-independent News Content Hub while preserving the existing public API.

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

The service remains responsible for acquisition, normalization, validation, deduplication, persistence and retrieval. LLM rewriting, persona-specific summarization, recommendation and TTS stay outside this service.

## 2. Layer boundaries

### domain

`app/domain/`

Provider-independent domain and identity logic:

- `ArticleCandidate`
- `TopicIngestionResult`
- `IngestionResult`
- canonical URL normalization
- provider-independent content fingerprinting

`ArticleCandidate.tag` remains as a compatibility alias for `topic`.

### providers

`app/providers/`

- `NewsProvider`: provider contract
- `ProviderRegistry`: runtime registry
- `ZakerProvider`: adapter around the existing ZAKER crawler

Routes and scheduler code no longer call `fetch_zaker()` directly.

### services

`app/services/ingestion.py`

`IngestionService` coordinates:

1. topic normalization,
2. bounded concurrent provider fetching,
3. repository persistence,
4. per-topic statistics,
5. partial/failure aggregation,
6. in-process run serialization.

### repositories

`app/repositories/`

Repository interfaces isolate persistence from application services. The current implementation uses SQLite, but service/provider code is persistence agnostic.

## 3. V0.2 persistence model

V0.2 introduces an authoritative normalized article model.

```text
articles
  id
  provider
  source_article_id
  canonical_url
  url
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

One article may therefore belong to multiple topics:

```text
Article
  +-- hot
  +-- tech
  +-- finance
```

The old `news` table remains as a V0.1 compatibility shadow table during the migration window.

## 4. Article identity and deduplication

An incoming article is considered an existing article when any stable identity matches:

1. `provider + source_article_id`, when the provider exposes one,
2. canonical URL,
3. normalized content hash.

### Canonical URL

Canonicalization currently:

- lowercases scheme/host,
- removes URL fragments,
- removes obvious tracking parameters such as `utm_*`, `from`, `ref`,
- removes default ports,
- sorts remaining query parameters,
- preserves semantic query parameters.

### Content hash

The content fingerprint uses normalized:

```text
title + summary
```

with Unicode NFKC normalization, whitespace normalization and case folding before SHA-256 hashing.

This intentionally provides conservative syndicated-content deduplication without introducing embeddings or LLM dependencies.

## 5. Multi-topic merge behavior

When a duplicate article is ingested from another topic:

- no second `articles` row is created,
- the new topic is inserted into `article_topics`,
- missing richer fields such as content/image may be backfilled,
- the ingestion result counts it as historical duplicate rather than a new article.

This fixes the V0.1 limitation where URL uniqueness caused later topic associations to be lost.

## 6. Automatic legacy migration

At database initialization V0.2:

1. creates `articles` and `article_topics` if needed,
2. reads existing V0.1 `news` rows,
3. computes canonical URL and content hash,
4. merges duplicate legacy rows when identities match,
5. creates topic associations,
6. preserves existing article IDs where possible.

The migration is idempotent and can safely run on every service startup.

## 7. Rollback compatibility

The V0.1 `news` table is retained during V0.2.

Newly created V0.2 articles are also shadow-written into `news` so that a code rollback to V0.1 still sees articles collected after the upgrade. Multi-topic information remains authoritative only in `article_topics`; the shadow row keeps one compatibility tag.

Cleanup runs against both the authoritative V0.2 article store and the V0.1 shadow table.

The legacy table should only be removed in a later version after the rollback window closes.

## 8. Public API compatibility

Existing endpoints remain:

- `GET /topics`
- `GET /news`
- `GET /news/{id}`
- `POST /fetch`
- `GET /scheduler/status`
- `POST /scheduler/config`
- `POST /scheduler/run`

`GET /news` continues returning the legacy `tag` field and additionally exposes:

- `topics`
- `canonical_url`
- `provider`
- `language`
- `content`
- `image_url`
- `updated_at`

When a request filters by a tag, the legacy `tag` response field is set to the requested matching topic.

## 9. SQLite behavior

Batch ingestion uses one connection/transaction rather than committing one article at a time.

Connections enable:

- foreign keys,
- busy timeout.

SQLite remains the recommended database for the current deployment scale.

## 10. Scheduler behavior

Scheduler engine state and fetch-job enabled state are treated separately.

Resume/pause/config operations can initialize the in-process scheduler engine when required, avoiding a persisted `enabled=true` state with no scheduler actually running.

Both scheduler and manual fetch operations now enter through `IngestionService`.

## 11. Tests added for V0.2

The branch includes tests covering:

- provider-independent ingestion,
- requested-topic normalization/deduplication,
- canonical URL normalization,
- content hash normalization,
- URL duplicate detection,
- multi-topic article association,
- existing V0.1 API behavior.

## 12. Next phases

After this schema foundation:

1. SQLite FTS5 search
2. richer article body/image extraction
3. improved ingestion result identity reporting
4. admin authentication for mutation endpoints
5. health/readiness/metrics
6. additional providers (RSS and curated sources)
7. removal of the V0.1 shadow table after the rollback window

PostgreSQL, Redis, Celery and Elasticsearch are intentionally not required for V0.2.

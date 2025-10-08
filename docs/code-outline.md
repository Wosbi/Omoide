# Code Outline

## Overview

Omoide is structured as a FastAPI backend paired with a React/Vite frontend. The backend provides media management APIs, background processing pipelines, and desktop integration hooks, while the frontend offers the user interface implemented with Material UI and React Router.【F:app/main.py†L17-L48】【F:frontend/src/App.tsx†L1-L27】

## Backend (`app/`)

### Application startup (`app/main.py`)
* Configures FastAPI, mounts API routers, schedules recurring maintenance scans, and handles lifecycle setup for processors, vector tables, ffmpeg availability, and task cleanup.【F:app/main.py†L17-L197】
* Exposes the UVicorn/webview entry point and integrates APScheduler for periodic scan jobs, chaining cleanup, scan, and processing tasks through the task pipeline.【F:app/main.py†L17-L131】【F:app/tasks/pipeline.py†L1-L42】

### Configuration (`app/config.py`)
* Manages environment-aware paths, profile bootstrap files, and runtime settings, including handling Docker vs. desktop paths and static asset resolution.【F:app/config.py†L1-L122】【F:app/config.py†L123-L182】
* Provides Pydantic-based settings models that control features such as scanning intervals, media directories, and ffmpeg configuration (not shown above but defined in the same module).【F:app/config.py†L183-L400】

### Database layer (`app/database.py`)
* Creates and resets the global SQLModel/SQLAlchemy engine, including sqlite-vec extension loading and pragmatic configuration when connections are established.【F:app/database.py†L1-L80】
* Exposes helpers to run Alembic migrations, fall back to metadata creation, and ensure vector search tables exist for embeddings.【F:app/database.py†L96-L200】

### Data models (`app/models.py`)
* Defines SQLModel tables for media, faces, persons, tags, timeline events, duplicate tracking, and processing tasks, with relationship wiring for ORM usage.【F:app/models.py†L1-L400】

### API routers (`app/api/`)
* Organized per feature (media, people, tags, search, duplicates, missing files, processors, tasks, configuration) and included into the FastAPI app during startup.【F:app/main.py†L30-L48】【F:app/api/__init__.py†L1-L11】
* Each router encapsulates request/response schemas defined under `app/schemas` and coordinates with task modules or services to satisfy requests.【F:app/schemas/media.py†L1-L81】【F:app/api/media.py†L1-L200】

### Background processing (`app/tasks/` & `app/processors/`)
* Task modules implement maintenance routines (e.g., cleaning missing files), media scanning, duplicate detection, hashing, and pipeline orchestration for chained processing.【F:app/tasks/maintenance.py†L1-L200】【F:app/tasks/pipeline.py†L1-L42】
* Processor modules define pluggable steps such as metadata extraction, duplicate analysis, embedding generation, and face detection, loaded dynamically at startup.【F:app/processors/base.py†L1-L200】【F:app/processors/duplicates.py†L1-L200】

### Utilities and services
* Support modules cover concurrency helpers, ffmpeg verification, logging configuration, screenshot generation, and reusable utility functions used throughout the backend.【F:app/concurrency.py†L1-L200】【F:app/logger.py†L1-L200】【F:app/ffmpeg.py†L1-L160】

## Frontend (`frontend/`)

### Application shell
* `src/main.tsx` bootstraps the React application with the theme context and renders the router-based `App` component within a Vite entry point.【F:frontend/src/main.tsx†L1-L40】
* `src/App.tsx` wires the Material UI theme, date localization, and task event context around the route configuration.【F:frontend/src/App.tsx†L1-L27】

### Routing and layout
* `src/routes.tsx` defines nested routes for search, media detail, tagging, maps, duplicates, configuration, and other feature areas, wrapping write-sensitive pages in read-only guards.【F:frontend/src/routes.tsx†L1-L88】
* `src/components/Layout.tsx` provides the shared header, navigation, and outlet container for routed content (including responsive drawers and action buttons).【F:frontend/src/components/Layout.tsx†L1-L200】

### Pages and feature modules
* `src/pages` contains page-level containers for dashboards, media browsing, person detail views, tagging workflows, duplicates review, configuration, and maintenance views that coordinate data fetching and UI composition.【F:frontend/src/pages/IndexPage.tsx†L1-L200】【F:frontend/src/pages/DuplicatesPage.tsx†L1-L200】
* Supporting React components under `src/components` implement reusable UI like media cards, grids, dialogs, tag editors, face management panels, and timeline widgets used across pages.【F:frontend/src/components/MediaGrid.tsx†L1-L200】【F:frontend/src/components/PersonHero.tsx†L1-L200】

### State management and services
* `src/stores/useListStore.ts` centralizes paginated list state with Zustand, providing reusable fetch/load/update helpers for infinite-scroll lists.【F:frontend/src/stores/useListStore.ts†L1-L120】
* `src/services` hosts API clients that wrap backend endpoints for media, people, tags, tasks, and configuration, enabling pages and components to interact with the FastAPI services.【F:frontend/src/services/media.ts†L1-L200】【F:frontend/src/services/config.ts†L1-L200】

### Styling and theming
* Theme configuration lives in `src/ThemeContext.tsx`, `src/theme.ts`, and `src/index.css`, combining Material UI theme toggling with Tailwind/CSS utilities for consistent styling across the UI.【F:frontend/src/ThemeContext.tsx†L1-L200】【F:frontend/src/theme.ts†L1-L200】

## Infrastructure & Tooling

* Docker and Makefile scripts orchestrate development, testing, and deployment workflows, including backend services, frontend build, and worker processes.【F:docker-compose.yml†L1-L120】【F:Makefile†L1-L200】
* `alembic/` holds migration scripts and env configuration for database schema evolution, while `versions/` contains generated migration history for the project.【F:alembic/env.py†L1-L171】【F:versions/6b0604629099_fix_person_embedding.py†L1-L80】


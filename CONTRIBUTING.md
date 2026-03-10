# Contributing to OpenGuardian

First, thanks for your interest in contributing to OpenGuardian! We welcome contributions to help improve the project.

## Development Environment Setup

This project uses `uv` for lightning-fast Python package management.

### Requirements

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) version 0.1+
- Docker & Docker Compose (for Neo4j testing)

### Setup

1. Clone the repository
2. Run `uv sync` to install dependencies and `pytest` modules
3. Set up the development database by running `docker compose up -d`
4. Copy `.env.example` to `.env` and fill out relevant API keys

## Architecture Context

Please review [ARCHITECTURE.md](ARCHITECTURE.md) before making deep changes to understand the separation between the Neo4j repository, FastAPI, LiteLLM summarizer, and connector plugins.

## Coding Standards

### Typing & Pydantic
OpenGuardian requires strict typing. You must use Pydantic v2 for data models and response schemas. No generic `dict` or `Any` types are allowed for returned data or graph event fields.

### Docstrings
All classes, methods, and functions mapped within the API layers and Database handlers **must** include comprehensive docstrings describing their signature and functionality. We follow standard Sphinx/Google style docstrings depending on module context.

## Submitting Pull Requests

1. **Fork the Repo & Create a Branch** for your feature or bug fix.
2. **Add Tests**: Provide unit/integration tests within the `tests/` directory ensuring new features are reliably validated.
3. **Commit your changes**: Ensure commit messages are clear and reference issues properly.
4. **Push & Create PR**: Briefly describe the problem you're addressing, your proposed solution, and attach relevant issue tracking IDs.

## Known Risks Library

To contribute new threat models to the framework, please create a markdown file under `/known-risks/` following the existing syntax required for our LLM context builder.

Your file should specify:
- Risk Context
- Trigger Categories (used by keyword-based risk loaders)
- Progression Pattern

Review the `REQUIREMENTS.md` file for exact Known Risk schema structure.

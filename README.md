# OpenGuardian

> A local-first, privacy-respecting network behavior monitoring framework.

OpenGuardian is an open-source, locally-run framework that monitors network behavior for a single user/device, constructs a Knowledge Graph from traffic data, and surfaces behavioral insights for guardians or administrators. It is designed for home or school environments with a strong emphasis on privacy and consent — guardians see activity categories, never raw domains.

## Features

- **Privacy by Design**: DNS queries and domains are hashed locally. Only narrative categories are processed and displayed.
- **Local Knowledge Graph**: Powered by Neo4j to track behaviors, temporal patterns, and relationships.
- **LLM Anomaly Detection**: Uses local or cloud LLMs (via LiteLLM) to detect behavioral anomalies compared to an established baseline.
- **Extensible Connectors**: Built-in support for Pi-hole v6, with an extensible `ConnectorProtocol` for extending data ingestion.
- **Known Risks Library**: Identifies recognized behavioral patterns (e.g., grooming progression) using extensible markdown-based risk models.

## Architecture

Please review [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed breakdown of the internal pipelines, graph schemas, and data flow.

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Python 3.11+
- Pi-hole v6 (running on the network)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/username/OpenGuardian.git
   cd OpenGuardian
   ```

2. Copy the environment template and configure it:
   ```bash
   cp .env.example .env
   # Edit .env to add your Neo4j password, LLM API keys, and Pi-hole credentials.
   ```

3. Start the Neo4j Graph Database:
   ```bash
   docker compose up -d
   ```

4. Install the dependencies and run the application:
   ```bash
   uv sync
   uv run openguardian
   ```

## API Documentation

When the application is running, the OpenAPI UI is available at `http://localhost:8000/docs`. All FastAPI endpoints provide strict Pydantic v2 schemas.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on our development workflow, submitting pull requests, and the coding standards we enforce.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

from fastapi import Request
from neo4j import AsyncDriver
from openguardian.connectors.registry import ConnectorRegistry

def get_driver(request: Request) -> AsyncDriver:
    """Provides dependency injected Neo4j AsyncDriver."""
    return request.app.state.driver

def get_registry(request: Request) -> ConnectorRegistry:
    """Provides dependency injected ConnectorRegistry singleton."""
    return request.app.state.registry

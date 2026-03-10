import importlib.util
import json
import logging
from pathlib import Path
from typing import Dict, Type
from pydantic import ValidationError

from openguardian.connectors.protocol import ConnectorProtocol
from openguardian.connectors.manifest import ConnectorManifest

logger = logging.getLogger(__name__)

CONNECTORS_DIR = Path(__file__).parent
# Typically, individual connectors reside in subdirectories of this folder.

class ConnectorRegistry:
    """
    Discovers, validates, and manages connector plugins at runtime.
    """
    def __init__(self):
        self._connectors: Dict[str, ConnectorProtocol] = {}
        self._manifests: Dict[str, ConnectorManifest] = {}

    def discover(self):
        """
        Scans the `connectors` directory for subdirectories containing a `connector.json` manifest.
        Validates the manifest, imports the module, and instantiates the connector.
        """
        logger.info(f"Scanning for connectors in {CONNECTORS_DIR}...")
        for plugin_dir in CONNECTORS_DIR.iterdir():
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("__"):
                continue

            manifest_path = plugin_dir / "connector.json"
            if not manifest_path.exists():
                continue

            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = ConnectorManifest.model_validate(manifest_data)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"Failed to validate manifest in {plugin_dir.name}: {e}")
                continue

            connector_path = plugin_dir / "connector.py"
            if not connector_path.exists():
                logger.error(f"Plugin {manifest.name} missing connector.py entrypoint")
                continue

            try:
                spec = importlib.util.spec_from_file_location(
                    f"openguardian.connectors.{plugin_dir.name}.connector",
                    connector_path
                )
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Assume the module exports a setup() function or a specific class.
                # Here we expect the module to have a `get_connector()` factory function.
                if hasattr(module, "get_connector"):
                    connector = module.get_connector()
                    self._connectors[manifest.name] = connector
                    self._manifests[manifest.name] = manifest
                    logger.info(f"Successfully loaded connector: {manifest.name} v{manifest.version}")
                else:
                    logger.error(f"Module {plugin_dir.name} missing `get_connector()` factory")
            except Exception as e:
                logger.error(f"Failed to load connector {manifest.name}: {e}")

    def list_connectors(self) -> Dict[str, ConnectorProtocol]:
        """Returns the dictionary of initialized connectors."""
        return self._connectors
    
    def list_manifests(self) -> Dict[str, ConnectorManifest]:
        """Returns the dictionary of validated connector manifests."""
        return self._manifests

registry = ConnectorRegistry()

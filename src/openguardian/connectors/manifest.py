from typing import Literal, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class ConnectorManifest(BaseModel):
    """
    Manifest schema for connector.json defined by plugins.
    """
    name: str = Field(description="Identifier of the connector.")
    version: str = Field(description="Version string of the plugin.")
    data_fields: List[str] = Field(default_factory=list, description="List of columns extracted.")
    privacy_class: Dict[str, Literal["raw_private", "derived_ok", "aggregate_ok", "pseudonymous"]] = Field(
        description="Privacy classification mapping for each data field yielded."
    )

    model_config = ConfigDict(extra="ignore")

"""Connector registry — factory pattern for dynamic connector lookup."""

from __future__ import annotations

import logging
from typing import Type

from interfaces import BaseConnector
from models import ConnectorConfig, SourceInfo, SourceType

logger = logging.getLogger(__name__)

_REGISTRY: dict[SourceType, Type[BaseConnector]] = {}


def register(source_type: SourceType):
    """Class decorator to register a connector implementation."""

    def wrapper(cls: Type[BaseConnector]):
        if source_type in _REGISTRY:
            logger.warning("Overwriting connector for %s", source_type)
        _REGISTRY[source_type] = cls
        return cls

    return wrapper


def get_connector_class(source_type: SourceType) -> Type[BaseConnector]:
    if source_type not in _REGISTRY:
        raise ValueError(f"No connector registered for source type: {source_type}")
    return _REGISTRY[source_type]


def create_connector(config: ConnectorConfig) -> BaseConnector:
    cls = get_connector_class(config.source_type)
    return cls(config)


def list_available_sources() -> list[SourceInfo]:
    return [cls.source_info() for cls in _REGISTRY.values()]


def get_source_info(source_type: SourceType) -> SourceInfo:
    cls = get_connector_class(source_type)
    return cls.source_info()


def registered_types() -> list[SourceType]:
    return list(_REGISTRY.keys())

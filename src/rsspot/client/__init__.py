"""Client entrypoints."""

from rsspot.client.async_client import AsyncSpotClient
from rsspot.client.singleton import (
    aclose_all_clients,
    clear_client_cache,
    configure,
    get_async_client,
    get_client,
    get_sync_client,
    list_profiles,
    set_active_profile,
    set_default_org,
    set_default_profile,
    set_default_region,
    use_org,
    use_profile,
    use_region,
)
from rsspot.client.sync_client import SpotClient

__all__ = [
    "AsyncSpotClient",
    "SpotClient",
    "aclose_all_clients",
    "clear_client_cache",
    "configure",
    "get_async_client",
    "get_client",
    "get_sync_client",
    "list_profiles",
    "set_active_profile",
    "set_default_org",
    "set_default_profile",
    "set_default_region",
    "use_org",
    "use_profile",
    "use_region",
]

from .api_client import BggApiClient
from .browser_client import BggBrowserClient
from .protocol import BggClientProtocol


def get_bgg_client() -> BggClientProtocol:
    """Return BggApiClient if an API token is configured, else BggBrowserClient."""
    from ..config import get_setting

    token = get_setting("bgg_api_token")
    if token:
        return BggApiClient(token)
    return BggBrowserClient()

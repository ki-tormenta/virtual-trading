from supabase import create_client, Client

from config.settings import settings

_client: Client | None = None


def get_supabase_client() -> Client:
    """Supabase クライアントのシングルトンを返す。"""
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    return _client

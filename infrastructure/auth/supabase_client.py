from supabase import create_client, Client

from config.settings import settings

_client: Client | None = None


def get_supabase_client() -> Client:
    """Supabase クライアントのシングルトンを返す。

    Raises:
        RuntimeError: SUPABASE_URL または SUPABASE_ANON_KEY が未設定の場合
    """
    global _client
    if _client is None:
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_ANON_KEY
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL と SUPABASE_ANON_KEY を環境変数または Streamlit Secrets に設定してください。"
            )
        _client = create_client(url, key)
    return _client

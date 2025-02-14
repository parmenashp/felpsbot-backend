from urllib.parse import urljoin

from pydantic import BaseSettings, PostgresDsn, RedisDsn


class Settings(BaseSettings):
    redis_url: RedisDsn
    postgres_url: PostgresDsn
    rabbitmq_url: str

    rabbitmq_queue_name: str
    rabbitmq_exchange_name: str

    auth0_client_id: str
    auth0_issuer: str = "https://felpsbot.us.auth0.com/"
    auth0_audience: str = "https://felpsbot.mitsuaky.com/api/"

    twitch_client_id: str
    twitch_client_secret: str
    twitch_api_base_url: str = "https://api.twitch.tv/helix/"
    twitch_oauth_url: str = "https://id.twitch.tv/oauth2/token"
    eventsub_secret_key: str

    backend_base_url: str = "http://localhost"
    log_level: str = "DEBUG"

    @property
    def eventsub_callback_url(self):
        return urljoin(self.backend_base_url, "/eventsub/callback")


settings = Settings()  # type: ignore

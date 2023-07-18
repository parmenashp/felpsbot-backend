import os

CALLBACK_URL = os.environ["BACKEND_BASE_URL"].rstrip("/") + "/eventsub/callback"
TWITCH_API_BASE_URL = "https://api.twitch.tv/helix/"
TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"

AUTH0_ISSUER = "https://felpsbot.us.auth0.com/"
AUTH0_AUDIENCE = "https://felpsbot.mitsuaky.com/api/"

RABBIMQ_URL = os.environ["RABBITMQ_URL"]
RABBIMQ_EXCHANGE = "eventsub"

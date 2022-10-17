# Felpsbot Backend

This is the backend of a personal project of mine which is a "twitch integration" for the streamer Felps.

It uses [FastAPI](https://fastapi.tiangolo.com/) web framework, [PostgreSQL](https://www.postgresql.org/) database and [Redis](https://redis.io/) as cache.

### Folders

`./api/` has the main API (not commited yet).

`./eventsub/` has the service responsible for receiving the Twitch Eventsubs

## Requirements

* Python 3.10 or later
* Docker ([How to install](https://docs.docker.com/engine/install/))
* Docker compose ([How to install](https://docs.docker.com/compose/install/))

## Installation

1. Clone the repository 

```bash
git clone https://github.com/mitsuaky/felpbot-backend
```

2. Open the `./api/` and `./eventsub/`

3. Rename the `.env.exemple` file to `.env` and fill with your credentials

## Usage

Use the docker compose to run the containers

```bash
docker compose up -d
```

Test if it's working going to documentation https://localhost:8050/docs

## Contributing
Pull requests are welcome.

## License
[GNU AGPLv3](https://choosealicense.com/licenses/agpl-3.0/)

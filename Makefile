update env:
	doppler secrets download --no-file --format env > .env

test:
	pytest --cov=src tests/
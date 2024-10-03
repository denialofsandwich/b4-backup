install:
	@poetry update
	@poetry install

unit-test:
	@poetry run pytest tests/unit_tests

build-test:
	@podman build -f Dockerfile.test -t b4_backup:0.1.0 .

full-test:
	@podman run --rm -it -v .:/code localhost/b4_backup:0.1.0

lint:
	@poetry run ruff .

lint-live:
	@poetry run ruff . --watch

lint-fix:
	@poetry run black . --line-length 100
	@poetry run ruff . --fix

pre-commit:
	@poetry run pre-commit run --all-files

serve-docs:
	@poetry run mkdocs serve

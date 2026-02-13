.PHONY: install test lint clean

install:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache

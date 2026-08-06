.PHONY: help completions release-assets clean-dist

help:
	@echo "Available targets:"
	@echo "  completions    Generate Click native shell completions"
	@echo "  release-assets Generate completions and build release artifacts"
	@echo "  clean-dist     Remove build artifacts"

completions:
	uv run python scripts/generate_completions.py

release-assets: clean-dist completions
	uv build

clean-dist:
	rm -rf dist build

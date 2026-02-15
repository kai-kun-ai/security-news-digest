IMAGE_NAME := security-news-digest
TAG := latest
CONFIG ?= config.yaml
OUTPUT_DIR ?= $(PWD)/output
FEEDS_FILE ?=
EXTRA_ARGS ?=

.PHONY: build run run-no-llm run-interests clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker image
	docker build -t $(IMAGE_NAME):$(TAG) .

run: build ## Run digest (default: with LLM)
	docker run --rm \
		-v $(PWD)/$(CONFIG):/app/config.yaml:ro \
		-v $(OUTPUT_DIR):/app/output \
		$(if $(FEEDS_FILE),-v $(abspath $(FEEDS_FILE)):/app/feeds.txt:ro,) \
		-e CODEX_API_KEY=$${CODEX_API_KEY:-} \
		-e OPENAI_API_KEY=$${OPENAI_API_KEY:-} \
		$(IMAGE_NAME):$(TAG) \
		$(if $(FEEDS_FILE),--feeds-file /app/feeds.txt,) \
		$(EXTRA_ARGS)

run-no-llm: build ## Run digest without LLM (heuristic mode)
	$(MAKE) run EXTRA_ARGS="--no-llm"

run-interests: build ## Run digest with interest filtering
	$(MAKE) run EXTRA_ARGS="--interests"

clean: ## Remove Docker image
	docker rmi $(IMAGE_NAME):$(TAG) 2>/dev/null || true

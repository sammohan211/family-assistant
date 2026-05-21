# shellcheck shell=bash
# Family Assistant operational helper — PRD §17.8.
#
# Source from ~/.bashrc on the desktop:
#   echo 'source ~/Projects/family_assistant/scripts/family.sh' >> ~/.bashrc
#   source ~/.bashrc
#
# What you get:
#   - COMPOSE_FILE exported so `docker compose up -d --build` always merges
#     the GPU overlay (the trap that silently drops the model onto CPU).
#   - fa-up / fa-down to bring the stack up (containers + migrations + model
#     warm + doctor) or take it down (containers stopped, volumes preserved).
#   - fa-status / fa-logs / fa-ops / fa-warm / fa-restart / fa-rebuild for
#     the highest-frequency ops.
#   - fa-doctor — one-keystroke "is it healthy?" diagnostic.
#
# OPERATIONS.md remains the source of truth for what each underlying command
# does; this file is a convenience layer.

# Project directory — override before sourcing if your checkout lives elsewhere.
export FAMILY_ASSISTANT_DIR="${FAMILY_ASSISTANT_DIR:-$HOME/Projects/family_assistant}"

# Always merge the GPU overlay. Plain `docker compose up -d --build` now picks
# up both files; running without it sends an 8B model onto CPU.
export COMPOSE_FILE="compose.yml:compose.gpu.yml"

# Read OLLAMA_MODEL from .env so fa-warm works regardless of shell env.
_fa_ollama_model() {
    local env_file="$FAMILY_ASSISTANT_DIR/.env"
    if [[ -r "$env_file" ]]; then
        local value
        value=$(grep -E '^OLLAMA_MODEL=' "$env_file" | tail -n1 | cut -d= -f2-)
        value="${value%\"}"; value="${value#\"}"
        value="${value%\'}"; value="${value#\'}"
        if [[ -n "$value" ]]; then
            printf '%s\n' "$value"
            return 0
        fi
    fi
    printf 'llama3.1:8b\n'
}

fa-up() {
    # `up -d --wait` blocks until healthchecks pass, so the exec / warm steps
    # below don't race the app and ollama start-periods.
    ( cd "$FAMILY_ASSISTANT_DIR" \
        && docker compose up -d --wait \
        && docker compose exec app alembic upgrade head ) \
        && fa-warm \
        && fa-doctor
}

fa-down() {
    # Stops + removes containers; volumes (Postgres, Ollama models, Caddy)
    # are preserved. `docker compose down -v` is intentionally not wrapped —
    # it wipes data and should stay an opt-in typed command.
    ( cd "$FAMILY_ASSISTANT_DIR" && docker compose down )
}

fa-status() {
    ( cd "$FAMILY_ASSISTANT_DIR" && docker compose ps "$@" )
}

fa-logs() {
    local svc="${1:-app}"
    [[ $# -gt 0 ]] && shift
    ( cd "$FAMILY_ASSISTANT_DIR" && docker compose logs -f --tail=200 "$svc" "$@" )
}

fa-ops() {
    ( cd "$FAMILY_ASSISTANT_DIR" && docker compose exec ollama ollama ps )
}

fa-warm() {
    local model
    model=$(_fa_ollama_model)
    echo "fa-warm: priming $model (first request after a rebuild loads ~20-40s of weights)"
    ( cd "$FAMILY_ASSISTANT_DIR" && docker compose exec ollama ollama run "$model" "hi" )
}

fa-restart() {
    ( cd "$FAMILY_ASSISTANT_DIR" && docker compose restart app )
}

fa-rebuild() {
    (
        cd "$FAMILY_ASSISTANT_DIR" \
            && git pull \
            && docker compose up -d --build \
            && docker compose exec app alembic upgrade head
    )
}

fa-doctor() {
    (
        cd "$FAMILY_ASSISTANT_DIR" || return 1
        echo "=== docker compose ps ==="
        docker compose ps
        echo
        echo "=== ollama ps ==="
        docker compose exec ollama ollama ps
        echo
        echo "=== GPU memory ==="
        if command -v nvidia-smi >/dev/null 2>&1; then
            nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
        else
            echo "(nvidia-smi not on PATH — run on the desktop host, not inside a container)"
        fi
        echo
        echo "=== last 20 app log lines ==="
        docker compose logs --tail=20 app
    )
}

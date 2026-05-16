"""Bootstrap FastAPI app so the Docker stack runs end-to-end before modules land."""

from fastapi import FastAPI

app = FastAPI(title="Family Assistant")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "Family Assistant", "status": "bootstrap"}

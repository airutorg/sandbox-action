FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv for dependency management inside the sandbox.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# /workspace is a host mount; hardlinks cannot cross filesystem boundaries.
ENV UV_LINK_MODE=copy

WORKDIR /workspace

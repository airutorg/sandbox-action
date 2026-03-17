FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Add ~/.local/bin to PATH (uv installs here).
ENV PATH="/root/.local/bin:$PATH"

# /workspace is a host mount; hardlinks cannot cross filesystem boundaries.
ENV UV_LINK_MODE=copy

# Install uv via official install script. This produces a glibc-linked binary
# that works with the sandbox DNS responder. The musl-linked static binary
# from ghcr.io/astral-sh/uv has DNS resolution issues in sandboxed networks
# (musl's getaddrinfo mishandles NOTIMP responses to AAAA queries).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /workspace

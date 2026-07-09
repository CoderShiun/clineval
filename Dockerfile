# Latest Python (see the 3.14 fallback note in Step 2 if a dep lacks 3.14 wheels).
FROM python:3.14-slim

# uv installs into a venv OUTSIDE /app so the runtime bind-mount does not shadow it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN pip install --no-cache-dir uv

WORKDIR /app

# Layer-cache dependencies: copy only manifests first, sync deps without the project.
COPY pyproject.toml uv.lock ./
RUN uv sync --extra dev --no-install-project --frozen

# Copy the rest and install the project itself (editable).
COPY . .
RUN uv sync --extra dev --frozen

CMD ["uv", "run", "pytest", "-q"]

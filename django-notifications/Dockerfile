FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED 1

# Install Poetry
RUN pip install poetry

# Add Poetry to PATH
ENV PATH="/root/.local/bin:$PATH"

# Copy Poetry project files
COPY pyproject.toml poetry.lock* /app/

# Install dependencies with Poetry
RUN poetry install --no-interaction --no-ansi --no-root

# Install redis-cli for debugging
RUN apt-get update && apt-get install -y redis-tools && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY . /app/

EXPOSE 8000

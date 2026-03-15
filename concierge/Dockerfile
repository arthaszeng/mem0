FROM python:3.12-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
LABEL org.opencontainers.image.name="memverse/concierge-mcp"
LABEL org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

EXPOSE 8766

CMD ["python", "-m", "server.mcp_server"]

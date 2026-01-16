# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build

# Version ARG busts cache when version changes
ARG APP_VERSION=dev

WORKDIR /app/frontend

# Install dependencies
COPY frontend/package.json ./
RUN npm install

# Build production bundle (version baked in via vite.config.ts)
COPY frontend/ ./
RUN echo "Building version: $APP_VERSION" && npm run build


# Stage 2: Runtime
FROM python:3.12-slim AS runtime

# Install nginx, supervisor, and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir uvicorn[standard]

# Copy backend code
COPY backend/app ./app

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Copy nginx config
COPY deploy/nginx.conf /etc/nginx/nginx.conf

# Copy supervisor config
COPY deploy/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create data directory
RUN mkdir -p /data && chown -R www-data:www-data /data

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/api/health || exit 1

# Run supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

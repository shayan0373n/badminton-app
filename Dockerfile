# Single image: FastAPI serves the API and the built client from one origin,
# so there is one thing to deploy, one log stream, and no CORS.

FROM node:22-slim AS client
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app *.py ./
COPY --chown=app:app database/ ./database/
COPY --chown=app:app --from=client /build/dist ./frontend/dist

# Sessions are pickled here; the compose file mounts a volume so a redeploy
# does not lose a night in progress.
RUN mkdir -p /app/sessions && chown app:app /app/sessions

USER app
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

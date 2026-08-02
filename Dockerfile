FROM node:22-alpine AS frontend-build
WORKDIR /workspace/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable \
    && corepack prepare pnpm@11.9.0 --activate \
    && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ISU_AI_DATA_DIR=/workspace/data \
    ISU_AI_MODELS_DIR=/workspace/models
WORKDIR /workspace
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /workspace/backend/requirements.txt
RUN python -m pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r /workspace/backend/requirements.txt
COPY backend/ /workspace/backend/
COPY photo_process/ /workspace/photo_process/
COPY unet/ /workspace/unet/
COPY features/train_stats.json /workspace/features/train_stats.json
COPY --from=frontend-build /workspace/frontend/dist /workspace/frontend/dist
RUN mkdir -p /workspace/data /workspace/models
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

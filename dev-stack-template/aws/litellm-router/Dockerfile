FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 AS adapter
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    LITELLM_LOCAL_MODEL_COST_MAP=True LITELLM_LOG=ERROR
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

FROM base
COPY --from=adapter /lambda-adapter /opt/extensions/lambda-adapter
ENV AWS_LWA_PORT=8080 AWS_LWA_READINESS_CHECK_PATH=/health \
    AWS_LWA_INVOKE_MODE=response_stream AWS_LWA_REMOVE_BASE_PATH=/pilot
COPY litellm_service.py routing.py litellm_config.yaml ./
CMD ["python", "-m", "uvicorn", "litellm_service:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]

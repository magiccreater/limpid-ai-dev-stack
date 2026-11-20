FROM public.ecr.aws/lambda/python:3.12

ENV HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/opt/huggingface OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
COPY requirements.txt fetch_model.py ${LAMBDA_TASK_ROOT}/
RUN python3 -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.0+cpu \
    && python3 -m pip install --no-cache-dir -r requirements.txt \
    && python3 fetch_model.py

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
COPY service.py ${LAMBDA_TASK_ROOT}/
CMD ["service.handle"]

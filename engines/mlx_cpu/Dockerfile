FROM python:3.12-slim-bookworm

RUN pip install --no-cache-dir "mlx[cpu]==0.32.0" "mlx-lm==0.31.3"

COPY engines/mlx_cpu/entrypoint.sh /opt/qwen/entrypoint.sh
RUN chmod +x /opt/qwen/entrypoint.sh

ENV HF_HOME=/models/cache \
    PORT=8000
EXPOSE 8000

ENTRYPOINT ["/opt/qwen/entrypoint.sh"]

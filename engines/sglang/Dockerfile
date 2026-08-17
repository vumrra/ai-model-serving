# 반드시 검증된 upstream digest를 넘긴다.
# docker build --build-arg BASE_IMAGE=lmsysorg/sglang:<tag>@sha256:<digest> .
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE

RUN digest="${BASE_IMAGE##*@sha256:}"; \
    if [ "${digest}" = "${BASE_IMAGE}" ] || [ "${#digest}" -ne 64 ]; then \
      echo "BASE_IMAGE must include an immutable 64-character sha256 digest" >&2; \
      exit 64; \
    fi; \
    case "${digest}" in \
      *[!0-9a-f]*) echo "BASE_IMAGE digest must be lowercase hexadecimal" >&2; exit 64 ;; \
    esac

LABEL org.opencontainers.image.base.name="${BASE_IMAGE}"

COPY engines/auth_proxy.py /opt/qwen/auth_proxy.py
COPY engines/sglang/entrypoint.sh /usr/local/bin/qwen-sglang-entrypoint
RUN chmod 0755 /usr/local/bin/qwen-sglang-entrypoint
RUN python3 -c "import fastapi, httpx, uvicorn"

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/qwen-sglang-entrypoint"]

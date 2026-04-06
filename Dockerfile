# MIRASTACK Plugin — Query VMetrics Python (multi-arch: linux/amd64, linux/arm64)
# Build context must be the monorepo root (mirastack/)
# so the local Python SDK is available.
#
# Build:
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     -f agents/oss/mirastack-plugin-query-vmetrics-python/Dockerfile .

FROM python:3.12-slim AS builder

WORKDIR /src

# Copy SDK first — install it so the plugin can reference "mirastack-sdk"
COPY sdk/oss/mirastack-sdk-python/ sdk/oss/mirastack-sdk-python/
RUN pip install --no-cache-dir sdk/oss/mirastack-sdk-python/

# Copy plugin and install it
COPY agents/oss/mirastack-plugin-query-vmetrics-python/ agents/oss/mirastack-plugin-query-vmetrics-python/
RUN pip install --no-cache-dir agents/oss/mirastack-plugin-query-vmetrics-python/

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/mirastack-plugin-query-metrics /usr/local/bin/mirastack-plugin-query-metrics
EXPOSE 50051
ENTRYPOINT ["mirastack-plugin-query-metrics"]

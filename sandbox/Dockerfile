FROM python:3.12.10-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.py /opt/judge/entrypoint.py
RUN python3 -I /opt/judge/entrypoint.py pch
USER 65534:65534
WORKDIR /work
ENTRYPOINT ["python3", "-I", "/opt/judge/entrypoint.py"]

FROM python:3.13-slim AS models
RUN apt-get update && apt-get install -y --no-install-recommends curl bzip2 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY fetch-models.sh /tmp/
RUN sh /tmp/fetch-models.sh /models

FROM python:3.13-slim
RUN useradd --create-home agent && mkdir /data && chown agent /data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=models /models /models
ENV MODEL_DIR=/models
COPY *.py ./
COPY static/ static/
COPY fixtures/ fixtures/
USER agent
EXPOSE 8765
CMD ["python","server.py","--bind","0.0.0.0","--db","/data/disputes.sqlite"]

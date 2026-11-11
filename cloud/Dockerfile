FROM python:3.11-slim
WORKDIR /app
COPY relay.py /app/relay.py
ENV WMM_CLOUD_HOST=0.0.0.0 WMM_CLOUD_PORT=8787 WMM_CLOUD_DB=/data/wmm-cloud.sqlite3
VOLUME ["/data"]
EXPOSE 8787
CMD ["python", "relay.py"]

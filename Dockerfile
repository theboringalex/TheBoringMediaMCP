FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TBMM_PORT=17830 \
    TBMM_DATA_DIR=/data

WORKDIR /app
COPY theboringmediamcp/app/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY theboringmediamcp/app/theboringmediamcp /app/theboringmediamcp

VOLUME /data
EXPOSE 17830
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('TBMM_PORT','17830'),timeout=4)" || exit 1
CMD ["python", "-m", "theboringmediamcp"]

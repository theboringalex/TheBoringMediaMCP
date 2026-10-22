FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TBMM_PORT=17830

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY app/theboringmediamcp /app/theboringmediamcp

EXPOSE 17830
CMD ["python", "-m", "theboringmediamcp"]

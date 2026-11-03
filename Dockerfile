FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /srv/osk
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home osk && mkdir /data && chown osk:osk /data
COPY --chown=osk:osk . .
USER osk
EXPOSE 8000
CMD ["gunicorn","--bind","0.0.0.0:8000","--workers","1","--threads","8","--timeout","90","--access-logfile","-","server:app"]

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fontconfig ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY docker/fonts/Montserrat-ExtraBold.ttf docker/fonts/Inter-Black.ttf /usr/share/fonts/truetype/shorteditor/
COPY docker/fonts/fonts.conf /etc/fonts/conf.d/99-shorteditor-aliases.conf
RUN fc-cache -f

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data /app/logs /models \
    && chown -R app:app /app /models

COPY --chown=app:app docker/entrypoint.sh /usr/local/bin/shorteditor-entrypoint
RUN chmod 755 /usr/local/bin/shorteditor-entrypoint

USER app
ENTRYPOINT ["/usr/local/bin/shorteditor-entrypoint"]
CMD ["python", "-m", "shorteditor.bot"]

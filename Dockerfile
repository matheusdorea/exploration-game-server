FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEADLESS=1 \
    PORT=12345

WORKDIR /app

COPY servidor.py  ./servidor.py
COPY shared/      ./shared/
COPY server/      ./server/

RUN touch shared/__init__.py server/__init__.py

RUN adduser --disabled-password --gecos "" gameuser
USER gameuser

EXPOSE ${PORT}/udp

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pgrep -f "servidor.py" > /dev/null || exit 1

CMD ["python", "servidor.py"]
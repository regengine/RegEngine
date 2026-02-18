FROM python:3.11-slim

WORKDIR /app

COPY services/internal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/internal/ .
COPY shared/ /app/shared/

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

WORKDIR /app

COPY services/internal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/internal/ .
COPY shared/ /app/shared/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

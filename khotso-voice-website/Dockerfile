FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .
RUN mkdir -p /app/data

EXPOSE 5000
CMD ["python", "app.py"]

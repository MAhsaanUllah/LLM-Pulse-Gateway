FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend /app/backend

# The gateway binds 0.0.0.0 inside the container; the compose file publishes it on
# 127.0.0.1 only, so the "bind to loopback" rule from the README still holds.
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

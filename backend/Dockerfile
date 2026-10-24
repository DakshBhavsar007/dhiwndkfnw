FROM python:3.12-slim

# Prevent python from buffering stdout/stderr and writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

# Create a non-root system user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install dependencies as root to system python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and committed data snapshots
COPY app/ ./backend/app/
COPY data/ ./backend/data/

# Ensure backend package initialization
RUN touch ./backend/__init__.py

# Ensure non-root user owns the app directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Healthcheck against the FastAPI /health endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]


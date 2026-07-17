FROM python:3.11-slim

WORKDIR /app

# Security: non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Fix permissions for non-root user
RUN chown -R app:app /app && chmod -R 755 /app

# Security: run as non-root
USER app

# Expose port
EXPOSE 8060

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8060/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8060"]

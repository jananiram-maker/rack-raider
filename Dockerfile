FROM python:3.11-slim

# Set working directory
WORKDIR /app
# Copy pre-built frontend static assets into /app/static
COPY ./static ./static
# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Prevent interactive prompts during apt-get
ARG DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn fastapi

# Copy application source
COPY my_agent ./my_agent
COPY main.py .

# Expose port
EXPOSE 8080

# Start command
CMD ["python", "main.py"]

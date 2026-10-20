FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create logs dir
RUN mkdir -p logs media staticfiles

# Non-root user for security
RUN addgroup --system carma && adduser --system --ingroup carma carma
RUN chown -R carma:carma /app
USER carma

EXPOSE 8000

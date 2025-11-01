# Simple Dockerfile for the Flask stock dashboard
FROM python:3.11-slim

# set workdir
WORKDIR /app

# system deps for building some wheels (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# copy requirements and install first for layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy app code
COPY . /app

# expose port
EXPOSE 5000

# runtime env
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# run
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
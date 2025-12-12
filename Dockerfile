FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromaprint-tools \
    gcc \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy app code
COPY . /app
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the app
CMD ["python", "app.py"]





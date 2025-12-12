# install system deps (ffmpeg + chromaprint-tools + minimal libs)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromaprint-tools \
    gcc \
    libmagic1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy python deps and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the app
COPY app.py .

# port used by Render
ENV PORT 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app", "--timeout", "120"]



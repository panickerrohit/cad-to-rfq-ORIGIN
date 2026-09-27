# API image: FastAPI + CadQuery + reportlab + pymupdf. Build from the api/ folder:
#   docker build -t rfq-api . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... rfq-api
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libx11-6 libxext6 libxrender1 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV JOBS_DIR=/data/jobs PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

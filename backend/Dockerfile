FROM python:3.12-slim

WORKDIR /app

# System dependencies: yosys + z3 for formal verification
RUN apt-get update && apt-get install -y --no-install-recommends \
    yosys \
    z3 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# SymbiYosys (sby) — clone and wire up manually (not a pip package)
RUN pip install --no-cache-dir click && \
    git clone --depth=1 https://github.com/YosysHQ/sby.git /opt/sby && \
    ln -sf /opt/sby/sbysrc/sby.py /usr/local/bin/sby && \
    chmod +x /opt/sby/sbysrc/sby.py

ENV PYTHONPATH=/opt/sby/sbysrc

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Runtime data directories (override with volumes in production)
RUN mkdir -p data/chromadb data/formal_work

EXPOSE 8000

# Ollama URL — override in docker-compose for service networking
ENV OLLAMA_BASE_URL=http://ollama:11434

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

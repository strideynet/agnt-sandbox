FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application code
COPY devoops/ devoops/

# Run as non-root user
RUN useradd -m -u 1000 devoops && chown -R devoops:devoops /app
USER devoops

# Run the agent
CMD ["python", "-m", "devoops"]

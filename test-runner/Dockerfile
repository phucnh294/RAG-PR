# Headless Chromium + Playwright behind a small FastAPI (see server.py). The tag pins the
# Playwright version; requirements.txt pins the same version of the Python package.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pytest.ini models.py runner.py server.py ./
COPY tests ./tests

# pwuser ships with the Playwright image (non-root; Chromium's sandbox works under it).
USER pwuser

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]

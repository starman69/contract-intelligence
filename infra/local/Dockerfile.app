# Common base image for the local-mode api + ingest services.
#
# Debian 11 / glibc 2.31 — matches the cryptography wheels we want and gives
# us msodbcsql18 for pyodbc against the local SQL Server container.
FROM python:3.11-slim-bullseye

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl gnupg2 ca-certificates unixodbc \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" \
      > /etc/apt/sources.list.d/microsoft.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Source mounted at /app/src by docker-compose; PYTHONPATH gets the right roots.
ENV PYTHONPATH=/app/src

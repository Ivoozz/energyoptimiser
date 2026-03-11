ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
# Alpine 3.23 uses python3.14
RUN apk add --no-cache \
    python3 \
    py3-pip \
    nodejs \
    npm \
    git \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
    tzdata

# Create a virtual environment to avoid "externally-managed-environment" errors in Python 3.14
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set up backend
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set up UI placeholder
WORKDIR /ui
RUN mkdir -p dist && echo "<h1>EnergyOptimiser</h1>" > dist/index.html

# Copy app source
COPY app/ /app/

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Expose the Ingress port
EXPOSE 8000

# Labels for Home Assistant 2026.3.1
LABEL \
    io.hass.name="EnergyOptimiser" \
    io.hass.description="Smart battery charging/discharging based on Nordpool prices and Solarman 6-program control." \
    io.hass.arch="armhf|aarch64|i386|amd64" \
    io.hass.type="addon" \
    io.hass.version="1.5.1"

CMD [ "/run.sh" ]

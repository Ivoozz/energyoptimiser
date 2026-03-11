ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    tzdata \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev

# Create venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Setup App
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app/ /app/
COPY run.sh /
RUN chmod a+x /run.sh

# Expose port
EXPOSE 8000

# Labels
LABEL \
    io.hass.name="EnergyOptimiser" \
    io.hass.description="Smart battery charging/discharging based on Nordpool prices and Solarman 6-program control." \
    io.hass.arch="armhf|aarch64|i386|amd64" \
    io.hass.type="addon" \
    io.hass.version="2026.3.0"

CMD [ "/run.sh" ]

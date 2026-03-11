# Stage 1: Build environment
ARG BUILD_FROM
FROM $BUILD_FROM AS builder

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install build dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    build-base \
    libffi-dev \
    openssl-dev \
    rust \
    cargo \
    git

# Create a virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python requirements
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Final runtime image
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install only runtime essentials
RUN apk add --no-cache \
    python3 \
    tzdata

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Setup App
WORKDIR /app
COPY app/ /app/
COPY run.sh /
RUN chmod a+x /run.sh

# Environment variables for performance and stability on Raspberry Pi
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV LOG_LEVEL=INFO

# Expose Ingress port
EXPOSE 8000

# Metadata Labels
LABEL \
    io.hass.name="EnergyOptimiser" \
    io.hass.description="Professional battery energy management optimized for Raspberry Pi." \
    io.hass.arch="armhf|aarch64|i386|amd64" \
    io.hass.type="addon" \
    io.hass.version="2026.3.5"

CMD [ "/run.sh" ]

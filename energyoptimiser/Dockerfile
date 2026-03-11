ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install critical dependencies for Python 3.14 and Alpine compatibility
# Adding rust/cargo as many wheels now require it for 3.14
RUN apk add --no-cache \
    python3 \
    py3-pip \
    tzdata \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
    rust \
    cargo \
    git \
    nodejs \
    npm

# Create a clean virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Setup App
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Setup UI dist directory
WORKDIR /app/static
RUN echo "<h1>EnergyOptimiser Loading...</h1>" > index.html

# Copy source code
WORKDIR /app
COPY app/ /app/
COPY run.sh /
RUN chmod a+x /run.sh

# Environment variables for Python 3.14
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Metadata Labels for Home Assistant 2026.3.1
LABEL \
    io.hass.name="EnergyOptimiser" \
    io.hass.description="Advanced energy management using Nordpool prices and Solarman 6-program control." \
    io.hass.arch="armhf|aarch64|i386|amd64" \
    io.hass.type="addon" \
    io.hass.version="2026.3.3"

CMD [ "/run.sh" ]

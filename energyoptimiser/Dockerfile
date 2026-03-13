ARG BUILD_FROM
FROM $BUILD_FROM

# Build arguments
ARG BUILD_ARCH

ENV LANG C.UTF-8

# Install Python and essential build dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-tz \
    bash \
    tzdata

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY app/requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application files
COPY app/ .

# Labels
LABEL \
    io.hass.name="EnergyOptimiser" \
    io.hass.description="Professional battery energy management with EnergyZero EPEX NL prices and Meteoserver solar forecasting." \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="2026.3.39" \
    maintainer="FixjeICT <info@fixjeict.nl>"

# Start script
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

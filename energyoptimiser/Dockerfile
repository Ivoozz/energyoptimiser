ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-tz

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ .

# Labels
LABEL \
    io.hass.name="EnergyOptimiser" \
    io.hass.description="Professional battery energy management with EnergyZero EPEX NL prices and Meteoserver solar forecasting." \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="2026.3.33" \
    maintainer="FixjeICT <info@fixjeict.nl>"

# Start script
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

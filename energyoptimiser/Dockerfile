ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    nodejs \
    npm \
    git \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev

# Create a virtual environment for Python
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set up backend
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set up UI
WORKDIR /ui
COPY ui/package.json .
# Ensure we have a dummy package.json if it's missing to avoid build failure
RUN if [ ! -f package.json ]; then echo '{"name": "ui", "version": "1.0.0"}' > package.json; fi
RUN npm install --legacy-peer-deps

# Copy app and ui source
COPY app/ /app/
COPY ui/ /ui/

# Build UI if src exists
RUN if [ -d "/ui/src" ]; then npm run build; else mkdir -p /ui/dist && echo "<h1>EnergyOptimiser UI</h1>" > /ui/dist/index.html; fi

# Start scripts
WORKDIR /
COPY run.sh .
RUN chmod a+x run.sh

# Expose the Ingress port
EXPOSE 8000

CMD [ "./run.sh" ]

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

# Set up backend
WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Set up UI
WORKDIR /ui
COPY ui/package.json .
RUN npm install --legacy-peer-deps

# Copy app and ui source
COPY app/ /app/
COPY ui/ /ui/

# Build UI
RUN npm run build

# Start scripts
WORKDIR /
COPY run.sh .
RUN chmod a+x run.sh

# Expose the Ingress port
EXPOSE 8000

CMD [ "./run.sh" ]

ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
RUN apk add --no-cache python3 py3-pip nodejs npm git

# Set up backend
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set up UI
WORKDIR /ui
COPY ui/package.json .
RUN npm install --legacy-peer-deps
COPY ui/ .
RUN npm run build

# Start scripts
WORKDIR /
COPY run.sh .
RUN chmod a+x run.sh

CMD [ "./run.sh" ]

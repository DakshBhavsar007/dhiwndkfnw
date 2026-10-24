# Stage 1: Build static SPA bundle
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies using package-lock for reproducible builds
COPY package*.json ./
RUN npm ci

# Copy source code and build production assets
COPY . .
RUN npm run build

# Stage 2: Serve static bundle via Nginx with backend reverse proxy
FROM nginx:alpine

# Remove default nginx website configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom reverse-proxy and SPA routing configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from builder stage
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Healthcheck testing local HTTP response
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

# Stage 1: build the static Vite bundle.
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: serve the built static files with nginx. Cloud Run requires listening on $PORT, so
# nginx's config is templated at startup (see docker-entrypoint.sh) rather than hardcoded to 80.
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.d/40-inject-api-url.sh
RUN chmod +x /docker-entrypoint.d/40-inject-api-url.sh

ENV PORT=8080
EXPOSE 8080

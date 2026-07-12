FROM node:20-alpine AS build
WORKDIR /app
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --ignore-optional --network-timeout 600000
COPY . .
ENV DISABLE_ESLINT_PLUGIN=true
ENV ENABLE_HEALTH_CHECK=false
ENV CI=false
RUN yarn build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
# SPA fallback so react-router deep links resolve + /healthz for docker healthcheck
RUN printf 'server {\n  listen 80;\n  server_name _;\n  root /usr/share/nginx/html;\n  index index.html;\n  location = /healthz { access_log off; add_header Content-Type text/plain; return 200 "ok\\n"; }\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 --start-period=10s \
  CMD wget -qO- --tries=1 --timeout=3 http://127.0.0.1/healthz || exit 1

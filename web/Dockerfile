FROM nginx:1.27-alpine

# The nginx image runs envsubst on /etc/nginx/templates/*.template at startup
ENV APP_UPSTREAM=app:5000 \
    NGINX_RESOLVER=127.0.0.11

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY proxy.conf /etc/nginx/snippets/proxy.conf
COPY index.html styles.css app.js /usr/share/nginx/html/

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/healthz || exit 1

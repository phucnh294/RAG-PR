# "myweb" — the Register Account page the Agents pipeline tests (system under test).
# Plain static HTML/JS served by nginx, no build step: the agents must see exactly the
# markup in site/myweb/, with nothing generated in between.
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site /usr/share/nginx/html

EXPOSE 8080

# Node 24 LTS - same major as local dev (the package-lock.json is written by its npm 11);
# vitest/vite require Node >= 22. Only the build stage uses Node, the image serves via nginx.
FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

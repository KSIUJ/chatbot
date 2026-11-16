# Node 24 LTS; vitest/vite require Node >= 22. Only the build stage uses Node,
# the image serves via nginx. pnpm pinned to "packageManager" in package.json.
FROM node:24-alpine AS build
WORKDIR /app
RUN npm install -g pnpm@12.18.0

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

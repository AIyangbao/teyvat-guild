# 构建阶段：Vite 8 要求 Node 20.19+ / 22.12+，直接用 22
FROM node:22-alpine AS build
WORKDIR /src
# 先拷清单装依赖：layer 缓存，改 src 不重装 node_modules
COPY package.json package-lock.json ./
# 国内服务器拉不动 npm 官方源时，加 --registry=https://registry.npmmirror.com
RUN npm ci
COPY . .
RUN npm run build

# 运行阶段：只要静态产物 + nginx
FROM nginx:alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

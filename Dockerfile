FROM node:20-alpine
RUN apk add --no-cache bash python3 py3-pip
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN bash build.sh
ENV NODE_ENV=production
CMD ["node", "dist/index.cjs"]
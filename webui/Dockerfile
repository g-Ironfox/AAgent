FROM golang:1.23-alpine AS builder

WORKDIR /src

# go.mod/go.sum 单独复制：这一层只依赖依赖清单，几乎不变，
# 镜像层缓存长期命中，模块只需下载一次
COPY go.mod go.sum ./
RUN go mod download

COPY . .

# 依赖已在镜像层内，源码再改也不会触发重新下载
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/webui .

FROM alpine:3.21

RUN apk add --no-cache ca-certificates \
    && addgroup -S app \
    && adduser -S -G app app

COPY --from=builder /out/webui /usr/local/bin/webui
USER app
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/webui"]
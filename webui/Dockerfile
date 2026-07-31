FROM golang:1.23-alpine AS builder

WORKDIR /src
COPY go.mod ./
RUN go mod download

COPY . .
RUN go mod tidy \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/webui .

FROM alpine:3.21

RUN apk add --no-cache ca-certificates \
    && addgroup -S app \
    && adduser -S -G app app

COPY --from=builder /out/webui /usr/local/bin/webui
USER app
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/webui"]
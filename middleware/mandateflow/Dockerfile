FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod ./
RUN go mod download
COPY main.go ./
RUN CGO_ENABLED=1 go build -o /mandate-gateway -ldflags="-s -w" .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates sqlite
COPY --from=build /mandate-gateway /mandate-gateway
EXPOSE 8182
ENV PORT=8182 MANDATEFLOW_DB=/data/mandateflow.db
VOLUME ["/data"]
USER 1000:1000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -qO- http://127.0.0.1:8182/health || exit 1
ENTRYPOINT ["/mandate-gateway"]

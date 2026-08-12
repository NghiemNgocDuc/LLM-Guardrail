# guardrail-scan — standalone Go port of scripts/scan_agent_skills.py.
#
#   make build          build the local binary (cli/guardrail-scan/guardrail-scan)
#   make test           run unit tests + the Python parity test (needs python3)
#   make vet            run go vet
#   make install        install the binary into $(PREFIX)/bin (default /usr/local)
#   make release        cross-compile static binaries into dist/
#   make clean          remove build artifacts

BINARY := guardrail-scan
LDFLAGS := -s -w
PREFIX ?= /usr/local
GO ?= go

TARGETS := darwin-amd64 darwin-arm64 linux-amd64 linux-arm64 windows-amd64 windows-arm64

.PHONY: all build test vet install clean release $(addprefix release-,$(TARGETS))

all: build

build:
	$(GO) build -trimpath -ldflags "$(LDFLAGS)" -o $(BINARY) .

test:
	$(GO) test ./...

vet:
	$(GO) vet ./...

install: build
	install -m 0755 $(BINARY) $(PREFIX)/bin/$(BINARY)

clean:
	rm -f $(BINARY)
	rm -rf dist

# Static cross-compiled binaries (no cgo anywhere in this module).
define release_rule
release-$(1):
	mkdir -p dist
	GOOS=$(word 1,$(subst -, ,$(1))) GOARCH=$(word 2,$(subst -, ,$(1))) CGO_ENABLED=0 $(GO) build -trimpath -ldflags "$(LDFLAGS)" -o dist/$(BINARY)-$(1)$(if $(findstring windows,$(1)),.exe,) .
endef
$(foreach t,$(TARGETS),$(eval $(call release_rule,$(t))))

release: $(addprefix release-,$(TARGETS))

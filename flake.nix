{
  description = "LLM Guardrails — reproducible dev shell (versions match CI and docker-compose)";

  # nixpkgs pinned to nixos-unstable commit 2fcb964 (2026-08-10).
  # The rev in the URL is the pin; the first `nix develop` (or `nix flake lock`)
  # records it in flake.lock together with the verified narHash — commit the
  # generated flake.lock so the pin is self-contained afterwards.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/2fcb964de67fcf60b43471c55d5d99e61a9ccb5a";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f:
        nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # OPA pinned to the exact binary docker-compose uses (openpolicyagent/opa:1.18.2),
      # because the nixpkgs open-policy-agent version at the pinned rev differs.
      opa_1_18_2 = { stdenv, fetchurl }:
        stdenv.mkDerivation {
          pname = "opa";
          version = "1.18.2";
          src = fetchurl {
            url = "https://github.com/open-policy-agent/opa/releases/download/v1.18.2/opa_linux_amd64_static";
            sha256 = "sha256-mQPlElrCgRBPLEtzcdEMw7dKmJM3Q/y/wXT5vwqyDeg="; # 9903e5125ac281104f2c4b7371d10cc3b74a98933743fcbfc174f9bf0ab20de8
          };
          sourceRoot = ".";
          unpackPhase = "true";
          installPhase = ''
            install -Dm755 $src $out/bin/opa
          '';
        };

      # Go pinned to 1.22.12 — exactly what CI's `go-version: "1.22"` resolves to.
      # nixpkgs at the pinned rev only ships Go 1.25–1.27, so this overrides it.
      go_1_22_12 = { stdenv, fetchurl }:
        stdenv.mkDerivation {
          pname = "go";
          version = "1.22.12";
          src = fetchurl {
            url = "https://go.dev/dl/go1.22.12.linux-amd64.tar.gz";
            sha256 = "sha256-T6T4abD3/Gux6yZg50ZX+/BM3SkLWu+QVYXIYFGzTUM="; # 4fa4f869b0f7fc6bb1eb2660e74657fbf04cdd290b5aef905585c86051b34d43
          };
          unpackPhase = "true";
          installPhase = ''
            mkdir -p $out
            tar -xzf $src -C $out
            chmod -R a-w $out/go
            chmod -R a+rX $out/go
          '';
        };
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            python312          # CI: setup-python 3.12
            pip
            maturin            # wheel build for guardrail_core (PyO3)
            cargo              # CI: dtolnay/rust-toolchain@stable
            rustc
            nodejs_22          # CI: setup-node 22
            redis              # docker-compose: redis:7-alpine (client; major matches)
            postgresql_16      # docker-compose: postgres:16-alpine (client; major matches)
            git
            gcc                # Rust linker for maturin builds
            cacert             # TLS roots for pip/cargo
            (opa_1_18_2 pkgs)  # docker-compose: openpolicyagent/opa:1.18.2 (exact)
          ];

          # Go 1.22.12 unpacked to $out/go — add its bin to PATH in shellHook.
          GOROOT_1_22 = "${(go_1_22_12 pkgs)}/go";

          shellHook = ''
            export PATH="$GOROOT_1_22/bin:$PATH"

            echo "LLM Guardrails dev shell"
            echo "  Python: $(python --version)  Node: $(node --version)"
            echo "  Go:    $(go version | cut -d' ' -f3)  Rust: $(rustc --version)"
            echo "  OPA:   $(opa version 2>/dev/null | head -n1 | cut -d' ' -f1-2 || echo 'n/a')"
            echo "  Postgres client: $(psql --version)"
            echo "  Redis client: $(redis-cli --version | sed 's/redis-cli //')"

            if [ ! -d .venv ]; then
              echo "First run: creating .venv and installing Python deps…"
              python -m venv .venv
              . .venv/bin/activate
              pip install --upgrade pip >/dev/null
              pip install -r requirements-dev.txt
            else
              . .venv/bin/activate
            fi

            echo "Python env: $(python --version) at .venv (activate: . .venv/bin/activate)"
            echo "Rust engine: maturin build --release --interpreter python --out wheels && pip install wheels/*.whl"
            echo "Frontend:    npm ci && npm run dev"
          '';
        };
      });
    };
}

{
  description = "cman";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";

    # the python package https://boisgera.github.io/pandoc/ currently needs pandoc 3.2.1 or lower
    # was trying with https://lazamar.co.uk/nix-versions/?package=pandoc but it's somehow totally off
    # nixos-25.05 has 3.6
    pandocpkgs.url = "github:nixos/nixpkgs?rev=3e2cf88148e732abc1d259286123e06a9d8c964a"; # 3.1.11.1

    # see https://pyproject-nix.github.io/

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      pandocpkgs,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        name = "cman";

        pkgs = nixpkgs.legacyPackages.${system};
        inherit (pkgs) lib;
        inherit (builtins) map;

        python = pkgs.python313;

        uv = pkgs.writeScriptBin "uv" ''
          #!${pkgs.zsh}/bin/zsh
          set -eu -o pipefail
          UV_PYTHON=${python}/bin/python ${pkgs.uv}/bin/uv --no-python-downloads $@
        '';

        prodPkgs = with pkgs; [
          # TODO there is also pandoc-katex ?
          pandocpkgs.legacyPackages.${system}.pandoc
          nodePackages_latest.katex # for the lib/node_modules/katex/dist files in preview
        ];

        devPkgs = (
          [
            uv
            python
          ]
          ++ (with pkgs; [
            ruff
            basedpyright
          ])
        );

        devLibs = with pkgs; [
          stdenv.cc.cc
          # zlib
          # libglvnd
          # xorg.libX11
          # glib
          # eigen
        ];

        devLdLibs = pkgs.buildEnv {
          name = "${name}-dev-ld-libs";
          paths = map (lib.getOutput "lib") devLibs;
        };

        devEnv = pkgs.buildEnv {
          name = "${name}-dev-env";
          paths = devPkgs ++ devLibs ++ prodPkgs;
        };

        pyproject = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
        moduleOverrides =
          final: prev:
          let
            # see https://github.com/TyberiusPrime/uv2nix_hammer_overrides/tree/main
            # I dont fully understand what we do here, we switch to setuptools instead of wheels?
            # for libs that need to build for nix? and we might have to add build dependencies?
            setuptools =
              prev_lib:
              prev_lib.overrideAttrs (old: {
                nativeBuildInputs =
                  (old.nativeBuildInputs or [ ]) ++ (final.resolveBuildSystem { setuptools = [ ]; });
              });
          in
          {
            "pandoc" = setuptools prev."pandoc";
          };
        modules =
          (pkgs.callPackage pyproject-nix.build.packages {
            python = python;
          }).overrideScope
            (
              lib.composeManyExtensions [
                pyproject-build-systems.overlays.default
                (pyproject.mkPyprojectOverlay { sourcePreference = "wheel"; })
                moduleOverrides
              ]
            );
        venv = modules.mkVirtualEnv "${name}-venv" pyproject.deps.default;
        inherit (pkgs.callPackages pyproject-nix.build.util { }) mkApplication;
        app = mkApplication {
          venv = venv;
          package = modules.cman;
        };
        package = pkgs.buildEnv {
          name = "${name}-env";
          paths = [ app ] ++ prodPkgs;
          postBuild = ''
            # TODO for example add some $out/share/zsh/site-functions/_name for completions
          '';
        };

      in
      {
        devShells.default = pkgs.mkShellNoCC {
          packages = [ devEnv ];
          LD_LIBRARY_PATH = "${pkgs.lib.makeLibraryPath [ devLdLibs ]}";
          shellHook = ''
            export PATH=$PWD/bin:$PATH
          '';
        };

        packages.default = package;
      }
    );
}

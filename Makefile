# Common development commands; override PYTHON to select a virtual environment.
PYTHON ?= python3
PACKAGE_REVISION ?= 1
.DEFAULT_GOAL := help
.PHONY: help run rpm deb windows build test coverage lint check clean clean-dry-run

# Additional Make goals let `make run path/to/checks.sfv` open a manifest at launch.
RUN_ARGUMENTS := $(filter-out run,$(MAKECMDGOALS))
ifneq ($(strip $(RUN_ARGUMENTS)),)
.PHONY: $(RUN_ARGUMENTS)
$(RUN_ARGUMENTS):
endif

# Keep command descriptions beside their targets so `make help` is the user-facing index.
help:
	@echo "make run [FILE]     Run the application, optionally opening a checksum file"
	@echo "make rpm            Build RPM packages from the local source"
	@echo "make deb            Build Debian packages from the working tree"
	@echo "make windows        Build the Windows portable application and installer"
	@echo "make build          Build Python source and wheel distributions"
	@echo "make test           Run unit tests"
	@echo "make coverage       Measure application-code test coverage"
	@echo "make lint           Run PyLint"
	@echo "make check          Run tests and PyLint"
	@echo "make clean          Remove generated builds and Python/tool caches"
	@echo "make clean-dry-run  Preview cleanup without deleting files"

# Prefer checkout code over any installed copy of the application.
run:
	PYTHONPATH=src $(PYTHON) -m bwverify.bwverify $(RUN_ARGUMENTS)

# Native package wrappers retain their platform-specific build requirements.
rpm:
	PACKAGE_REVISION="$(PACKAGE_REVISION)" bash scripts/build-rpm.sh

deb:
	PACKAGE_REVISION="$(PACKAGE_REVISION)" bash scripts/build-deb.sh

# The Windows builder owns PyInstaller and optional NSIS setup from its PowerShell environment.
windows:
	powershell.exe -ExecutionPolicy Bypass -File scripts/build-windows.ps1

# Python distributions remain separate from native package builds and their toolchains.
build:
	$(PYTHON) -m build

# Check source imports without requiring an editable installation.
test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

# Coverage stays separate from check so a basic developer install needs no extra tool.
coverage:
	PYTHONPATH=src $(PYTHON) -m coverage run -m unittest discover -s tests -v
	$(PYTHON) -m coverage report -m

# Run the same static checks locally and in continuous integration.
lint:
	PYTHONPATH=src $(PYTHON) -m pylint --persistent=no src tests scripts/clean.py \
		scripts/generate_package_changelogs.py

check: test lint

# Cleanup also works directly through Python on systems without Make.
clean:
	$(PYTHON) scripts/clean.py

clean-dry-run:
	$(PYTHON) scripts/clean.py --dry-run

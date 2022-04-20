VENV_PATH?=venv
PYTHON?=python3

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
	rm -rf dist build
	rm -rf .pytest_cache
	rm -rf .tox
	rm -rf "$(VENV_PATH)"

venv:
	"$(PYTHON)" -m venv "$(VENV_PATH)"
	"$(VENV_PATH)"/bin/pip install --upgrade pytest tox asynctest
	"$(VENV_PATH)"/bin/pip install --upgrade flake8 isort
	"$(VENV_PATH)"/bin/pip install --editable .
	# Needed for setup.py
	"$(VENV_PATH)"/bin/pip install --upgrade wheel docutils pypandoc restructuredtext_lint pygments

test: venv
	. "$(VENV_PATH)"/bin/activate ; \
	  "$(VENV_PATH)"/bin/pytest --exitfirst tests
	# Check if README.org converts correctly to rst for PyPI
	"$(PYTHON)" setup.py check -r -s >/dev/null

fulltest: venv
	. "$(VENV_PATH)"/bin/activate ; \
	  tox
	flake8 stig tests
	isort --check-only stig/**/*.py tests/**/*.py
	"$(PYTHON)" setup.py check -r -s >/dev/null

release:
	pyrelease CHANGELOG ./stig/__init__.py

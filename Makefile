PYTHON=		python3
SOURCE=		bobcat_rtpusher
VENV=		venv
DISTDIRS=	*.egg-info build dist


all:

$(VENV): $(VENV)/.depend

$(VENV)/.depend: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install -e .
	touch $(VENV)/.depend

upgrade-venv::
	$(VENV)/bin/pip install -r requirements.txt --upgrade
	$(VENV)/bin/pip install -e .

wheel: $(VENV)
	$(VENV)/bin/python setup.py sdist bdist_wheel

upload:
	twine upload --repository-url $(BOBCAT_PYPI) \
		dist/$(SOURCE)-*.whl \
		dist/$(SOURCE)-*.tar.gz

lint: $(VENV)
	$(VENV)/bin/pylama $(SOURCE)

typecheck: $(VENV)
	$(VENV)/bin/mypy $(SOURCE)

clean:
	rm -fr $(DISTDIRS)

realclean: clean
	rm -fr $(VENV)

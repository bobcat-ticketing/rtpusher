PYTHON=		python3
SOURCE=		bobcat_rtpusher
VENV=		venv
DISTDIRS=	*.egg-info build dist

BOBCAT_PYPI?=	https://pypi.bobcat.kirei.se/simple/


all:

$(VENV): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -i $(BOBCAT_PYPI) -r requirements.txt
	$(VENV)/bin/pip install -e .
	touch $(VENV)

upgrade-venv:: $(VENV)
	$(VENV)/bin/pip install -i $(BOBCAT_PYPI) -r requirements.txt --upgrade
	$(VENV)/bin/pip install -e .

wheel:
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

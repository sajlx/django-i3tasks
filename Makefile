

.PHONY: virtualenv_create
virtualenv_create:
	@echo "Creating virtualenv"
	@python3 -m venv venv

.PHONY: virtualenv_activate
virtualenv_activate:
	@echo "Activating virtualenv"
	@echo "run 'source venv/bin/activate'"


.PHONY: package_build
package_build:
	@echo "Clean old package build"
	@rm -rf dist
	@rm -rf build
	@rm -rf django_i3tasks.egg-info
	@echo "Building package"
	@python setup.py sdist bdist_wheel


.PHONY: package_upload
package_upload:
	@echo "Upload package"
	@twine upload dist/*

.PHONY: urls
urls:
	@echo "https://medium.com/@muhammad-haseeb/building-your-own-django-package-a-step-by-step-guide-8a8906d9010a"
	@echo "https://github.com/sajlx/django-i3tasks"
	@echo "https://pypi.org/project/django-i3tasks/"
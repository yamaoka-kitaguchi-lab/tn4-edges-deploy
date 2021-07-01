.PHONY: all
all: update

.PHONY: setup
setup:
	git pull
	pipenv update

.PHONY: edge
edge: setup
	pipenv run terraform
	date -u --iso-8601=seconds > .ts-last-update

.PHONY: vlan
vlan: setup
	pipenv run boring
	date -u --iso-8601=seconds > .ts-last-update

.PHONY: sync
sync:
	git reset HEAD --
	git add .ts-last-update
	git commit -m "Provisioning: $(shell date +%c)"
	git push origin main

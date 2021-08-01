# tn4-edges-deploy
[![](https://img.shields.io/github/issues/yamaoka-kitaguchi-lab/tn4-edges-deploy)](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy/issues) [![](https://img.shields.io/github/last-commit/yamaoka-kitaguchi-lab/tn4-edges-deploy)](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy/commits/main) [![](https://img.shields.io/github/license/yamaoka-kitaguchi-lab/tn4-edges-deploy)](LICENSE)

[![asciicast](https://asciinema.org/a/mthfyktmWhtAYrzyvysIvZ5qn.svg)](https://asciinema.org/a/mthfyktmWhtAYrzyvysIvZ5qn?autoplay=1)

Playbook and helper utilities to deploy Tn4 edges using NetBox as IPAM/DCIM. This toolset is designed to support the following:

- aa
- bb
- cc

**CAUTION:** *The author does not intend to reuse the helpers*. These are provided only to improve the efficiency of the Tn4 edges deployment.

## Usage
### STEP0: Clone repository and setup secrets

```
% git clone --depth 1 https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy
% cd tn4-edged-deploy
% echo -n "SECRET_PASSWORD_OF_THIS_REPOSITORY" | sha256sum | cut -d " " -f 1 > .secrets/vault-pass.txt
% openssl aes-256-cbc -d -in helpers/tn3/vault.tar.gz.enc -pass file:.secrets/vault-pass.txt |\
  tar xz --overwrite -C helpers/tn3
```

### STEP1: Seeding the NetBox for initial setup

```
% pipenv run seed
```

### STEP2: Provisioning edges according to the NetBox

```
% pipenv run migrate
```

## Developer's hints
When you are stuck in Ansible, commands `pipenv run dryrun` and `pipenv run develop` may help.

### Known issues and workarounds

- As of version v2.11.10, 

### Create vault.tar.gz.enc
Install `openssl` command to create AES256-CBC encrypted vault. All files under `helpers/tn3` are ignored by Git, but `*.enc` is not. Push it to GitHub and share the content for the consistency.

```
% cd tn3/helpers
% tar cz vault | openssl aes-256-cbc -e -pass file:../../.secrets/vault-pass.txt > vault.tar.gz.enc
```

### Structures
As of August 1st, 2021.

```
% tree -a -I ".git|.vscode|__pycache__|*.conf|*.cfg"
.
├── backup
│   ├── config.2021-08-01@01-44-01
│   └── config.2021-08-01@02-11-31
├── .gitignore
├── helpers
│   ├── devices.py
│   ├── docker-compose.yml
│   ├── interfaces.py
│   ├── migrate.py
│   ├── orphan-vlans.json
│   ├── port-migration.json
│   ├── seed.py
│   ├── .tmuxinator.yml
│   ├── tn3
│   │   ├── vault
│   │   │   ├── configs
│   │   │   ├── configs.staged
│   │   │   ├── hosts
│   │   │   └── vlans
│   │   │       ├── core-o1.vlan.txt
│   │   │       ├── core-o2.vlan.txt
│   │   │       ├── core-s1.vlan.txt
│   │   │       ├── core-s2.vlan.txt
│   │   │       └── vlans.txt
│   │   └── vault.tar.gz.enc
│   └── vlans.py
├── inventories
│   ├── production
│   │   ├── group_vars
│   │   │   └── all
│   │   │       ├── ansible.yml
│   │   │       └── vault.yml
│   │   ├── netbox.py
│   │   └── port-migration.json
│   └── staging
│       ├── group_vars
│       │   └── all
│       │       └── ansible.yml
│       └── hosts.yml
├── LICENSE
├── Pipfile
├── Pipfile.lock
├── playbook.log
├── README.md
├── roles
│   └── juniper
│       ├── tasks
│       │   ├── finalization.yml
│       │   ├── main.yml
│       │   └── migration.yml
│       └── templates
│           └── config.j2
├── .secrets
│   ├── googleapi.json
│   ├── vault-pass.txt
│   └── vault-pass.txt.example
└── site.yml

21 directories, 36 files
```

```
% scc .
───────────────────────────────────────────────────────────────────────────────
Language                 Files     Lines   Blanks  Comments     Code Complexity
───────────────────────────────────────────────────────────────────────────────
YAML                        10       136       10         8      118          0
Python                       6      1144      174        32      938        220
JSON                         1      2262        0         0     2262          0
Jinja                        1        71       11         9       51         18
License                      1        24        4         0       20          0
Markdown                     1        76        6         0       70          0
gitignore                    1       316       69        89      158          0
───────────────────────────────────────────────────────────────────────────────
Total                       21      4029      274       138     3617        238
───────────────────────────────────────────────────────────────────────────────
Estimated Cost to Develop (organic) $104,198
Estimated Schedule Effort (organic) 5.823731 months
Estimated People Required (organic) 1.589556
───────────────────────────────────────────────────────────────────────────────
Processed 82740 bytes, 0.083 megabytes (SI)
───────────────────────────────────────────────────────────────────────────────
```

## Authors and responsibilities
The initial work is as a part of the RA position at the request of Prof. Kitaguchi. The original author maintains this repository only during the RA employment period and will not be responsible for any troubles after the period.

- **MIYA, Taichi** - *Initial work* - [@mi2428](https://github.com/mi2428)

## License
This is free and unencumbered public domain software. For more information, see [http://unlicense.org/](http://unlicense.org/) or the accompanying [LICENSE](LICENSE) file.

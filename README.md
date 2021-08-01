# tn4-edges-deploy
[![](https://img.shields.io/github/issues/yamaoka-kitaguchi-lab/tn4-edges-deploy)](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy/issues) [![](https://img.shields.io/github/last-commit/yamaoka-kitaguchi-lab/tn4-edges-deploy)](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy/commits/main) [![](https://img.shields.io/github/license/yamaoka-kitaguchi-lab/tn4-edges-deploy)](LICENSE)

[![asciicast](https://asciinema.org/a/mthfyktmWhtAYrzyvysIvZ5qn.svg)](https://asciinema.org/a/mthfyktmWhtAYrzyvysIvZ5qn?autoplay=1)

Playbook and helper utilities to deploy Tn4 edges using NetBox as IPAM/DCIM. This toolset is designed to support the following:

- Seeding the NetBox for reducing the cost of browser-based registration operations
- Provisioning edges according to registered information of the NetBox

**CAUTION:** *The author doesn't intend to reuse the helpers*. These are provided only to improve the efficiency of the Tn4 edges deployment.

## Getting started
Skip step 1 if you don't need it.

### Step 0: Clone repository and setup secrets
To begin with, shallow clone this repository and decrypt the vault for both steps 1 and 2. Ask someone for the secret.

```
% git clone --depth 1 https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy
% cd tn4-edged-deploy
% echo -n "SECRET_PASSWORD_OF_THIS_REPOSITORY" | sha256sum | cut -d " " -f 1 > .secrets/vault-pass.txt
% openssl aes-256-cbc -d -in helpers/tn3/vault.tar.gz.enc -pass file:.secrets/vault-pass.txt |\
  tar xz --overwrite -C helpers/tn3
```

Next, create a new Python virtual environment and build the requirements. This may take a while.

```
% pipenv update
```

Finally, if you need to seed the NetBox, put a JSON key file of the Google Cloud API renamed `googleapi.json`.

```
% ls .secrets
googleapi.json  vault-pass.txt  vault-pass.txt.example
```

### Step 1: Seeding the NetBox for initial setup
Following items must be manually created prior to the seeding.

- **Regions:** Add new regions named *Ookayama Campus*, *Suzukakedai Campus*, and *Tamachi Campus* with slugged *ookayama*, *suzukake*, and *tamachi*. You may add a parent region named *Tokyo Institute of Technology* with slugged *tokyo-tech* to clarify their hierarchical relationships.
- **Device Types:** Add a new device type named *EX4300-48MP* with slugged *ex4300-48mp*. The interfaces must include *irb* so as to bind the management IP address of the instance. If some sites need stacked of *EX4300-48MP*, you should add an another device type for them. In the case of 2-stacked, add a device type named *EX4300-48MP 2-Stacked* with slugged *ex4300-48mp-st2*. See also [known issues and workarounds](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy#known-issues-and-workarounds) below.
- **Device Roles:** Add a new device role named *Edge Switch* with slugged *edge-sw*.
- **Tags:** Add a new tag named *PoE* with slugged *poe*.

Check the following two spreadsheets storing DCIM and IPAM initial records. Both two require authentication.

- [NetBox Seeds for Tn4 Edge Deployment](https://docs.google.com/spreadsheets/d/19ZUxcU-pdpwuNDDOA8u9IaQyuXxwpZh1X7uRygeo7Hw)
- [NetBox Seeds for Tn4 Edge Migration](https://docs.google.com/spreadsheets/d/11M9m7-C7Ogvuow7F5OG4U--TBk4gwETUcWTZWEJGCOY)

Launch the batfish with docker-compose:

```
% docker-compose -f helpers/docker-compose.yml up -d
```

Seed the NetBox. Note that there is an API limit in the free plan of Google Cloud API - 100 API calls per 100 seconds.
If the number of port migration sheets is more than 90, consider seeding it in several installments.

```
% pipenv run seed
```

If the seeding is successful, following two files will be output.

```
% jq < helpers/orphan-vlans.json | bat -l json
% jq < helpers/port-migration.json | bat -l json
```

### Step 2: Provisioning edges according to the NetBox
Provisioning is performed only for devices whose *Status* is *Active*. The following information is gathered from the NetBox:

- **Management IP address:** Use device's primary IPv4 address to login.
- **VLANs:** Create VLANs with registered names and descriptions.
- **Interfaces**
  - **Description:** Configure description.
  - **Enabled:** Configure administrative shutdown as needed.
  - **VLAN:** Configure tagged and untagged VLANs. If the *Mode* is *Tagged* and *Untagged VLAN* is specified, then *Untagged VLAN* is configured as a native VLAN ID.
  - **PoE:** Enable PoE feature if the interface has the *PoE* tag.
  - **Speed:** Enable link speed auto-negotiation for all interfaces.
  - **LAG:** Create link aggregation group with LACP activated.

Playbook will carry out the following tasks sequentially. Note that the uplink interfaces are skipped to reconfigure.

1. Enable NETCONF
1. Backup the current config, e.g., minami7_before.cfg
1. Configure interfaces according to the NetBox registration
1. Backup the current config, e.g., minami7_after.cfg

Kick Ansible and pray for provisioning. The larger the number of target hosts, the longer it takes to build the dynamic inventory - approximately 10 hosts/minute.

```
% pipenv run migrate
```

You can check the update by:

```
% cd backup/config.2021-08-01@01-44-01
% colordiff -u minami7_before.cfg minami7_after.cfg | bat
```

## Developer's hints
When you are stuck in Ansible, commands `pipenv run dryrun` and `pipenv run develop` may help.

### Known issues and workarounds
See also [issues](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy/issues) and [pull requests](https://github.com/yamaoka-kitaguchi-lab/tn4-edges-deploy/pulls).

- The current version (v2.11.10) of NetBox doesn't perform chassis number auto-increment. Therefore, the interface number of Virtual Chassis is not unique, and deployment with Ansible becomes harder. For the temporal workaround, you must add the *device type* of every stacked device.

### Create vault.tar.gz.enc
Create AES256-CBC encrypted vault with the `openssl` command. Git ignores all files under the directory `helpers/tn3`, but files ended with `*.enc` are not. **Do not forget to push it back to GitHub and share the content to keep consistency.**

```
% cd helpers/tn3
% tar cz vault | openssl aes-256-cbc -e -pass file:../../.secrets/vault-pass.txt > vault.tar.gz.enc
```

### Manual batch configurations via SSH
Use the [tmuxinator](https://github.com/tmuxinator/tmuxinator) to create multiple connections in one command.
Edit `helpers/.tmuxinator.yml` specifying the targets, then type:

```
% cd helpers
% tmuxinator local
```

### Structures
As of August 1st, 2021.

```
% tree -a -I ".git|.vscode|__pycache__|*.conf|*.cfg"
.
├── backup                            # Configs gathered by Ansible
│   ├── config.2021-08-01@01-44-01
│   └── config.2021-08-01@02-11-31
├── .gitignore
├── helpers
│   ├── devices.py                    # Collect devices from spreadsheet
│   ├── docker-compose.yml            # Launch batfish
│   ├── interfaces.py                 # Collect current interface configs
│   ├── migrate.py                    # Collect migration rules from spreadsheet
│   ├── orphan-vlans.json             # List of unknown VLANs defined in Tn3 edges
│   ├── port-migration.json           # Summary of interface migration
│   ├── seed.py                       # Seeder script
│   ├── .tmuxinator.yml               # Settings of tmuxinator
│   ├── tn3
│   │   ├── vault
│   │   │   ├── configs               # log-o1
│   │   │   ├── configs.staged
│   │   │   ├── hosts
│   │   │   └── vlans
│   │   │       ├── core-o1.vlan.txt  # show config vlans | display set
│   │   │       ├── core-o2.vlan.txt
│   │   │       ├── core-s1.vlan.txt
│   │   │       ├── core-s2.vlan.txt
│   │   │       └── vlans.txt         # cat *.vlan.txt | sort | uniq
│   │   └── vault.tar.gz.enc
│   └── vlans.py                      # Collect VLAN definitions
├── inventories
│   ├── production
│   │   ├── group_vars
│   │   │   └── all
│   │   │       ├── ansible.yml       # Parameters for Ansible
│   │   │       └── vault.yml         # Secret parameters (encrypted)
│   │   └── netbox.py                 # Dynamic inventory script
│   └── staging
│       ├── group_vars
│       │   └── all
│       │       └── ansible.yml
│       └── hosts.yml
├── LICENSE
├── Pipfile
├── Pipfile.lock                      # Auto-generated, ignored by Git
├── playbook.log                      # Auto-generated, ignored by Git
├── README.md
├── roles
│   └── juniper                       # For JUNOS (EX-series, QFS-series edges)
│       ├── tasks
│       │   ├── finalization.yml      # Playbook for password reset
│       │   ├── main.yml
│       │   └── migration.yml         # Playbook for the edge deploy
│       └── templates
│           └── config.j2             # Configuration template
├── .secrets
│   ├── googleapi.json
│   ├── vault-pass.txt
│   └── vault-pass.txt.example
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
Jinja                        1        71       11         9       51         18
License                      1        24        4         0       20          0
Markdown                     1       226       44         0      182          0
gitignore                    1       316       69        89      158          0
───────────────────────────────────────────────────────────────────────────────
Total                       20      1917      312       138     1467        238
───────────────────────────────────────────────────────────────────────────────
Estimated Cost to Develop (organic) $40,396
Estimated Schedule Effort (organic) 4.062804 months
Estimated People Required (organic) 0.883358
───────────────────────────────────────────────────────────────────────────────
Processed 56816 bytes, 0.057 megabytes (SI)
───────────────────────────────────────────────────────────────────────────────
```

## Authors and responsibilities
The initial work is as a part of the RA position at the request of Prof. Kitaguchi. The original author maintains this repository only during the RA employment period and will not be responsible for any troubles after the period.

- **MIYA, Taichi** - *Initial work* - [@mi2428](https://github.com/mi2428)

## License
This is free and unencumbered public domain software. For more information, see [http://unlicense.org/](http://unlicense.org/) or the accompanying [LICENSE](LICENSE) file.


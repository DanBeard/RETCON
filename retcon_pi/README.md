Build a system with a custom config, meta layers and provide a directory namespace to identify additional meta assets.

The custom config specifies system ```profile=deb12-acme```. This profile includes in-tree layers plus custom layers to demonstrate how to:
* Install a list of packages (example-developer/essential.yaml)
* Install a third-party repo key which could be used to authenticate and install packages from that repo (acme-sdk-v1.yaml)
* Install a script from the host which may have sensitive info, run it to simulate pseudo auto-installation, then securely clean up.

Usage of the options file injects additional variables into the build to be picked up by operations in acme-sdk-v1.yaml.

```text
examples/custom_layers/
|-- acme
|   |-- meta
|   |   `-- acme-sdk-v1.yaml
|   `-- setup-functions
|-- acme.options
|-- config
|   `-- acme-integration.cfg
|-- meta
|   `-- example-developer
|       `-- essential.yaml
|-- profile
|   `-- deb12-acme
`-- README.md
```

```bash
./build.sh -c acme-integration -D examples/custom_layers/ -N acme -o examples/custom_layers/acme.options
```

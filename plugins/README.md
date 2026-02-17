# Provider Plugins

This directory is the install target for provider plugins.

Unpack plugin tarballs here, maintaining the vendor/plugin structure:

    plugins/
      vmware/
        vcenter/        ← tar xzf vmware-vcenter-0.1.0.tar.gz
      cisco/
        nxos/           ← tar xzf cisco-nxos-0.1.0.tar.gz

Then run the installer from the plugin directory:

    cd plugins/vmware/vcenter
    ./install.sh

The contents of this directory (except this README) are gitignored.

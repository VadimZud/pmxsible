#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) Vadim Zudin <zudinvadim@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
    name: members
    short_description: Inventory Proxmox nodes on current cluster
    version_added: "0.0.1"
    author:
      - Vadim Zudin <zudinvadim@gmail.com>
    description:
      - Get nodes of current Proxmox cluster.
      - "Uses a configuration file as an inventory source, it must end in C(members.yml) or C(members.yaml)."
      - Work only on Proxmox node (pmxcfs required).
    options:
      plugin:
        description: The name of this plugin, it should always be set to V(vadimzud.pmxsible.members) for this plugin to recognize it as it's own.
        required: true
        choices: ['vadimzud.pmxsible.members']
        type: str      
    extends_documentation_fragment:
      - constructed
      - inventory_cache
"""

EXAMPLES = """
# cluster.members.yml
plugin: vadimzud.pmxsible.members
"""

import json

from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable
from ansible.errors import AnsibleError
from ansible.module_utils.common.text.converters import to_native


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = "vadimzud.pmxsible.members"

    def verify_file(self, path):
        valid = False
        if super(InventoryModule, self).verify_file(path):
            if path.endswith(("members.yaml", "members.yml")):
                valid = True
            else:
                self.display.vvv(
                    'Skipping due to inventory source not ending in "members.yaml" nor "members.yml"'
                )
        return valid

    def add_host(self, hostname, host_vars):
        self.inventory.add_host(hostname)

        for k, v in host_vars.items():
            self.inventory.set_variable(hostname, k, v)

        strict = self.get_option("strict")
        self._set_composite_vars(self.get_option("compose"),
                                 host_vars,
                                 hostname,
                                 strict=strict)
        self._add_host_to_composed_groups(self.get_option("groups"),
                                          host_vars,
                                          hostname,
                                          strict=strict)
        self._add_host_to_keyed_groups(self.get_option("keyed_groups"),
                                       host_vars,
                                       hostname,
                                       strict=strict)

    def populate(self, results):
        for hostname, host_vars in results.items():
            self.add_host(hostname, host_vars)

    def get_inventory(self):
        try:
            with open("/etc/pve/.members") as f:
                members = json.load(f)

            results = {}

            for hostname, node_info in members["nodelist"].items():
                host_vars = {
                    "ansible_host": node_info["ip"],
                    "online": bool(node_info['online']),
                }
                results[hostname] = host_vars

            return results
        except Exception as e:
            raise AnsibleError('Cannot load /etc/pve/.members: %s' %
                               to_native(e))

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)

        self._read_config_data(path)

        cache_key = self.get_cache_key(path)
        user_cache_setting = self.get_option("cache")

        attempt_to_read_cache = user_cache_setting and cache
        cache_needs_update = user_cache_setting and not cache

        if attempt_to_read_cache:
            try:
                results = self._cache[cache_key]
            except KeyError:
                cache_needs_update = True
        if not attempt_to_read_cache or cache_needs_update:
            results = self.get_inventory()
        if cache_needs_update:
            self._cache[cache_key] = results

        self.populate(results)

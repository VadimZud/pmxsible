#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) Vadim Zudin <zudinvadim@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
module: ansible_collection
short_description: manages ansible collections
version_added: "1.0.0"
description:
  - Manages ansible collections.
options:
  name:
    description:
      - The name of a Ansible collection to install or the url of the remote package.
      - This can be a list and contain version specifiers.
    type: list
    elements: str
  requirements:
    description:
      - The path to a ansible-galaxy requirements file, which should be local to the remote system.
    type: str
  state:
    description:
      - The state of module
    type: str
    choices: [ absent, forcereinstall, latest, present ]
    default: present
  extra_args:
    description:
      - Extra arguments passed to ansible-galaxy collection.
    type: str
  chdir:
    description:
      - cd into this directory before running the command.
    type: path
  executable:
    description:
      - The executable or pathname for the ansible-galaxy executable.
    type: path
    default: ansible-galaxy
attributes:
  check_mode:
    support: none
  diff_mode:
    support: none
  platform:
    platforms: posix
author:
  - Vadim Zudin (@VadimZud) <zudinvadim@gmail.com>
"""

EXAMPLES = """
- name: Install community.postgresql collection
  vadimzud.pmxsible.ansible_collection:
    name: community.postgresql

- name: Install community.postgresql collection on version 2.4.1
  vadimzud.pmxsible.ansible_collection:
    name: community.postgresql:==2.4.1

- name: Install community.postgresql collection with version specifiers
  vadimzud.pmxsible.ansible_collection:
    name: community.postgresql:>2.2.1,<2.4.1,!=2.3.5

- name: Install multi collections
  vadimzud.pmxsible.ansible_collection:
    name:
      - community.postgresql
      - community.rabbitmq

- name: Install multi collections with version specifiers
  vadimzud.pmxsible.ansible_collection:
    name:
      - community.postgresql:>2.2.1,<2.4.1,!=2.3.5
      - community.rabbitmq:>1.1.0,<1.2.0,!=1.1.1

- name: Install a collection in a git repository using https
  vadimzud.pmxsible.ansible_collection:
    name: git+https://github.com/VadimZud/pmxsible.git
      
- name: Install a collection in a git repository using the latest commit on the branch 'main'
  vadimzud.pmxsible.ansible_collection:
    # Don`t use
    # name: git+https://github.com/VadimZud/pmxsible.git,main
    # or
    # name: 'git+https://github.com/VadimZud/pmxsible.git,main'
    # Internally ansible will split string to list with ',' delimiter
    #(['git+https://github.com/VadimZud/pmxsible.git', 'main']).
    # For version specifiers it isn`t problem because vesion specifier doesh`t
    # looks like collection name and module can fix it.
    # For branch name or commit identifier it isn`t true, so use list syntax
    # explicitly:
    name: 
      - git+https://github.com/VadimZud/pmxsible.git,main
    #or
    #name: ['git+https://github.com/VadimZud/pmxsible.git,main']

- name: Install a collection in a git repository using ssh
  vadimzud.pmxsible.ansible_collection:
    name: git@github.com:VadimZud/pmxsible.git

- name: Install a collection from a local git repository
  vadimzud.pmxsible.ansible_collection:
    name: git+file:///home/user/path/to/repo_name.git

- name: Install a collection from a tarball
  vadimzud.pmxsible.ansible_collection:
    name: /tmp/my_namespace-my_collection-1.0.0.tar.gz

- name: Install a collection from source directory
  vadimzud.pmxsible.ansible_collection:
    name: ./my_namespace/my_collection/
    chdir: /path/to/my_namespace/parent/

- name: Install a collection from a tarball  without contacting any distribution servers
  vadimzud.pmxsible.ansible_collection:
    name: /tmp/my_namespace-my_collection-1.0.0.tar.gz
    extra_args: --offline
      
- name: Install multiple collections with a requirements file
  vadimzud.pmxsible.ansible_collection:
    requirements: /my_app/requirements.yml

- name: Install community.postgresql, forcing reinstallation if it's already installed
  vadimzud.pmxsible.ansible_collection:
    name: community.postgresql
    state: forcereinstall
"""

RETURN = '''
cmd:
  description: ansible-galaxy command used by the module
  returned: always
  type: list
  elements: str
  sample: ['ansible-galaxy', 'collection', 'install', 'community.postgresql', 'community.rabbitmq']
'''

from ansible.module_utils.basic import AnsibleModule
from collections.abc import Iterator
import shutil
import json
import collections
import os.path

VERSION_SPECIFIER_PREFIXES = ('*', '!=', '==', '>=', '>', '<=', '<')


def fix_orphaned_version_specifiers(name):
    '''Join orphaned version specifiers with collection name.
    
    If user defines `name` option as string, ansible will split name to list
    with `,` delimiter. So collection name with multiple version specifiers
    (`name: community.postgresql:>2.2.1,<2.4.1,!=2.3.5` for example)
    turns into list with orphaned version specifiers
    (`['community.postgresql:>2.2.1', '<2.4.1', '!=2.3.5']`).
    This function fix this problem.
    '''

    fixed_name = []
    collection_name_components = []
    for item in name:
        if item.lstrip().startswith(VERSION_SPECIFIER_PREFIXES):
            collection_name_components.append(item)
        else:
            if collection_name_components:
                fixed_name.append(','.join(collection_name_components))
            collection_name_components = [item]
    if collection_name_components:
        fixed_name.append(','.join(collection_name_components))

    return fixed_name


def installed_collections_dict(list_result):
    '''Convert `ansible-galaxy collection list --format=json` out to collection->install_paths dict'''

    list_result = json.loads(list_result)
    collections_dict = collections.defaultdict(list)

    for path, collections_list in list_result.items():
        for collection in collections_list:
            collections_dict[collection].append(
                os.path.join(path, *collection.split('.')))

    return collections_dict


def remove_version_specifiers(name):
    '''Generate collection names without version specifiers'''

    for item in name:
        parts = item.split(':')
        if len(parts) > 1 and parts[1].startswith(VERSION_SPECIFIER_PREFIXES):
            yield parts[0]
        else:
            yield item


def collection_uninstall(name, list_result):
    '''Missing `ansible-galaxy collection uninstall` emulation'''
    installed_collections = installed_collections_dict(list_result)

    changed = False

    for collection in remove_version_specifiers(name):
        if collection in installed_collections:
            changed = True
            for path in installed_collections[collection]:
                shutil.rmtree(path)

    return changed


def run_module():
    state_args = dict(
        # ansible-galaxy command hasn`t uninstall action.
        # So this special case for absent state.
        # I use list action for find installed collections locations.
        # I will remove finded packages manually.
        absent=['list', '--format=json'],
        present=['install'],
        latest=['install', '--upgrade'],
        forcereinstall=['install', '--force'],
    )

    module_args = dict(
        state=dict(type='str',
                   default='present',
                   choices=list(state_args.keys())),
        name=dict(type='list', elements='str'),
        requirements=dict(type='str'),
        extra_args=dict(type='str'),
        chdir=dict(type='path'),
        executable=dict(type='path', default='ansible-galaxy'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        required_one_of=[['name', 'requirements']],
        mutually_exclusive=[['name', 'requirements']],
    )

    result = dict(
        changed=False,
        rc=None,
        stderr=None,
        stdout=None,
        cmd=None,
    )

    state = module.params['state']
    name = module.params['name']
    requirements = module.params['requirements']
    extra_args = module.params['extra_args']
    chdir = module.params['chdir']
    executable = module.params['executable']

    if name:
        name = fix_orphaned_version_specifiers(name)

    if extra_args:
        extra_args = extra_args.split()
    else:
        extra_args = []

    if '/' not in executable:
        executable_path = shutil.which(executable)
        if not executable_path:
            module.fail_json(msg='%s executable not found' % executable,
                             **result)
        executable = executable_path

    if state == 'absent':
        targets = []
    else:
        if requirements:
            targets = ['-r', requirements]
        else:
            targets = name

    cmd = [executable, 'collection', *state_args[state], *extra_args, *targets]

    result['cmd'] = cmd

    rc, stdout, stderr = module.run_command(cmd, cwd=chdir)

    result['rc'] = rc
    result['stdout'] = stdout
    result['stderr'] = stderr

    if rc != 0:
        module.fail_json(msg='%s exit with non-zero code' % executable,
                         **result)

    if state == 'absent':
        try:
            result['changed'] = collection_uninstall(name, stdout)
        except Exception as e:
            module.fail_json(msg='collection uninstall failed: %s' % e,
                             **result)
    else:
        result['changed'] = 'was installed successfully' in stdout

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()

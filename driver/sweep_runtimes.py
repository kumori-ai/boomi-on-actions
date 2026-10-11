"""Delete leftover test runtimes. Only runtimes named gha-* that are attached to the CI environment (or to
nothing) are ever deleted; the live runtime and the live environment are refused by id, whatever the name.

    python sweep_runtimes.py                 delete every leftover test runtime
    python sweep_runtimes.py --target <id>   try to delete one runtime by id (used to prove the refusal)
"""
import sys
from boomi_api import IDS, call, query

PREFIX = 'gha-'


def refusal(atom, attachments):
    """Why this runtime must not be deleted, or None when it is a leftover test runtime."""
    envs = [a['environmentId'] for a in attachments if a.get('atomId') == atom['id']]
    if atom['id'] == IDS['live_atom']:
        return 'it is the live runtime'
    if IDS['live_env'] in envs:
        return 'it is attached to the live environment'
    if not str(atom.get('name', '')).startswith(PREFIX):
        return f"its name does not start with {PREFIX}"
    if any(e != IDS['ci_env'] for e in envs):
        return 'it is attached to an environment other than the CI one'
    return None


def sweep(target=None):
    """Returns (deleted names, refused [(name, why)])."""
    atoms, attachments = query('Atom'), query('EnvironmentAtomAttachment')
    deleted, refused = [], []
    for atom in atoms:
        if target and atom['id'] != target:
            continue
        why = refusal(atom, attachments)
        if why:
            if target or str(atom.get('name', '')).startswith(PREFIX):
                refused.append((atom.get('name'), why))
            continue
        code, d = call('DELETE', f"Atom/{atom['id']}")
        if code != 200:
            refused.append((atom.get('name'), f'delete answered HTTP {code}'))
        else:
            deleted.append(atom.get('name'))
    return deleted, refused


if __name__ == '__main__':
    target = sys.argv[sys.argv.index('--target') + 1] if '--target' in sys.argv else None
    deleted, refused = sweep(target)
    print('deleted:', deleted or 'nothing')
    for name, why in refused:
        print(f'REFUSED {name}: {why}')
    if target and not deleted:
        sys.exit(2)

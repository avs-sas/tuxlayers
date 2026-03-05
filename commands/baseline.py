'''Implements all baseline handling for tuxlayers'''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import glob
import hashlib
import logging
import os
import pprint

import click
import pydriller
import git
from git import Repo

from configuration import data
from shared.helpers import exit_with_error, remove_empty_folders, exit_application

# Logging setup...
logger = logging.getLogger(__name__)

def _get_repo_commit(path, baseline_set):
    """Helper to find the commit for a specific path in a baseline set."""
    abspath = os.path.abspath(path)
    for entry in baseline_set:
        if abspath in entry:
            return entry[abspath]
        # Check for matching absolute paths in the keys
        for entry_path, commit in entry.items():
            if os.path.abspath(entry_path) == abspath:
                return commit
    return None

@click.command()
@click.option(
    '--workdir', '-w', required=True,
    type=click.Path(exists=True),
    default=".",
    help='Workdir that holds the repo(s) to analyze.')
def listsubmodules(workdir):
    '''Lists all submodules and their respective baselines.
     Meant for debugging and/or repo analysis.'''
    workdir = normalize_workdir_path(workdir)
    baselines = get_baselines_from_path(workdir, 0, False)[0]
    if not baselines_are_valid(baselines):
        logger.error("Invalid baseline set!")


@click.command()
@click.option(
    '--workdir', '-w', required=True,
    type=click.Path(exists=True),
    default=".",
    help='Workdir that holds the repo(s) to analyze.')
def showbaselines(workdir):
    '''Lists all available baselines and checks the repo vor validity
     (e.g. all submodules contain the same ordered set of baselines).'''
    workdir = normalize_workdir_path(workdir)
    baselines, order = get_baselines_from_path(workdir, 0, True)
    if not baselines_are_valid(baselines):
        logger.error("Invalid baseline set!")
    else:
        if not baselines:
            logger.info("No baselines found!")
        else:
            logger.info("Baselines are valid. Avaliable baselines are:")
            for baseline in order:
                logger.info("- %s", baseline)


@click.command()
@click.option(
    '--workdir', '-w', required=True,
    type=click.Path(exists=True),
    default=".",
    help='Workdir that holds the repo(s) to analyze.')
@click.argument('baseline', type=click.STRING)
def addbaseline(workdir, baseline):
    '''Adds a baseline with the given name to the repository structure.'''
    add_baseline_internal(workdir, baseline)

def _get_oldest_baseline(workdir, baselines):
    """Finds the name of the oldest baseline (the one farthest from HEAD)."""
    main_repo = Repo(workdir)
    distance = -1
    oldest_baseline = None

    for baseline_name, baseline_set in baselines.items():
        repo_commit = _get_repo_commit(workdir, baseline_set)
        if repo_commit is None:
            # Fallback for complex structures or error handling
            continue

        # Count commits between baseline and HEAD
        result = int(main_repo.git.rev_list("--count", f"{repo_commit}..{main_repo.head.commit}"))
        if result > distance:
            distance = result
            oldest_baseline = baseline_name

    return oldest_baseline

@click.command()
@click.option(
    '--workdir', '-w', required=True,
    type=click.Path(exists=True),
    default=".",
    help='Workdir that holds the repo(s) to analyze.')
@click.option(
    '--all', '-a', is_flag=True, required=False,
    type=click.BOOL, default=False, help='If set, all baselines are removed.')
@click.option(
    '--clean', '-c', is_flag=True, required=False,
    type=click.BOOL, default=False, help='If set, also performs git clean -xfd on all repos after reset, removing non-tracked files.')
@click.argument('baseline', type=click.STRING, default="")
def reverttobaseline(workdir, baseline, all, clean):
    '''Sets the repository structure to the commit before the one marked
     by the baseline (removing all later commits and the baseline commit).'''
    workdir = normalize_workdir_path(workdir)
    baselines = get_baselines_from_path(workdir, 0, True)[0]

    if all:
        logger.info("Resetting all repos to before the first baseline entry.")
        if len(baselines) == 0:
            if clean:
                clean_workdir(workdir)
            exit_application("Repository contains no baselines, nothing to remove!")

        oldest_baseline = _get_oldest_baseline(workdir, baselines)
        if oldest_baseline is None:
            exit_with_error("Repo in " + workdir + " contains no marked baselines!")

        logger.info("Oldest baseline in set: %s", oldest_baseline)
        reset_hard_to_baseline(workdir, baselines[oldest_baseline])
    else:
        if not baseline:
            exit_with_error("Either specify all or provide a baseline name")
        if baseline not in baselines:
            exit_with_error("Invalid baseline: " + baseline)

        logger.info("Resetting all repos to the commit before baseline %s", baseline)
        reset_hard_to_baseline(workdir, baselines[baseline])

    if clean:
        clean_workdir(workdir)

def clean_workdir(workdir):
    logger.info("Cleaning workdir: %s", workdir)
    try:
        repo = Repo(workdir)
        repo.git.clean(['-xfd'])
        repo.git.submodule(['foreach', '--recursive', 'git', 'clean', '-xfd'])
    except git.exc.GitError as error:
        exit_with_error("Git error: " + str(error))

def _get_baseline_name_from_commit(commit):
    """Extracts the baseline name from a commit message."""
    return get_message_parts(commit.message)[2].strip()

def _get_baseline_pairs(baselines, baseline_order):
    """Generates pairs of baselines for patch extraction."""
    baseline_pairs = []
    for i in reversed(range(len(baseline_order))):
        current_name = baseline_order[i]
        # Use first commit in the baseline set to get metadata (they should be identical across repos)
        first_entry = baselines[current_name][0]
        first_commit = list(first_entry.values())[0]

        pair = {
            "from": baselines[current_name],
            "name": _get_baseline_name_from_commit(first_commit),
            "parent": ""
        }

        if i > 0:
            pair["to"] = baselines[baseline_order[i-1]]

        if i + 1 < len(baseline_order):
            prev_name = baseline_order[i+1]
            prev_entry = baselines[prev_name][0]
            prev_commit = list(prev_entry.values())[0]
            pair["parent"] = _get_baseline_name_from_commit(prev_commit)

        baseline_pairs.append(pair)
    return baseline_pairs

@click.command()
@click.option(
    '--workdir', '-w', required=True,
    type=click.Path(exists=True),
    default=".",
    help='Workdir that holds the repo(s) to analyze.')
@click.option(
    '--includebaseline', '-i', is_flag=True, required=False,
    type=click.BOOL, default=False,
    help='''If set, all (starting) empty baseline
        commits are included in the patch set.''')
@click.argument('outpath', type=click.Path(exists=False))
def createpatches(workdir, outpath, includebaseline):
    '''Walks through repo and creates patches and patchset configurations
       For each found baseline. Each patchset starts at the baseline
       - taking its name - and contains all commits as single patches
       until the next baseline. Each baseline has the previous one as a parent.
       '''
    if os.path.exists(outpath):
        exit_with_error("Outpath may not exist: " + outpath)
    os.mkdir(outpath)
    patchdir = os.path.join(outpath, "patches")
    os.mkdir(patchdir)

    workdir = normalize_workdir_path(workdir)
    baselines, baseline_order = get_baselines_from_path(workdir, 0, True)
    if not baselines_are_valid(baselines):
        exit_with_error("Invalid baseline configuration!")

    logger.info("Storing patches in %s", patchdir)
    baseline_pairs = _get_baseline_pairs(baselines, baseline_order)

    logger.info(pprint.pformat(baseline_pairs, indent=2))

    for pair in baseline_pairs:
        if not (3 <= len(pair) <= 4):
            exit_with_error("Invalid baseline pair configuration!")
        result = extract_patches(
            workdir,
            workdir,
            patchdir,
            pair,
            includebaseline)
        patch_layer_content = result.to_json(indent=4)
        logger.info(patch_layer_content)
        layer_filename = os.path.join(outpath, pair["name"] + ".json")
        with open(layer_filename, "w", encoding="utf-8") as layer_file:
            layer_file.write(patch_layer_content)

def add_baseline_internal(workdir, baseline):
    '''Internal implementation of adding a baseline to a given git repository'''
    workdir = normalize_workdir_path(workdir)
    logger.info("Adding baseline commit %s to each repo under %s",
                baseline, workdir)
    add_recursive_commit(workdir,  create_baseline_string(baseline))

def extract_patches(path, base_dir, patchdir, baseline_pair, include_baseline):
    '''Extracts patches from a repository and puts then in a given folder'''
    repo = Repo(path)
    result = data.PatchLayer(
        id=baseline_pair["name"],
        parent=baseline_pair["parent"],
        title="Auto-generated layer for baseline: "
        + baseline_pair["name"],
        description="")
    for module in repo.submodules:
        sub_repo = extract_patches(
            module.module().working_tree_dir,
            base_dir,
            patchdir,
            baseline_pair,
            include_baseline)
        result.patches.extend(sub_repo.patches)
    sub_repo = extract_patches_for_repo(
        path,
        base_dir,
        patchdir,
        baseline_pair,
        include_baseline)
    result.patches.extend(sub_repo.patches)
    return result


def _get_commit_hashes(path, from_commit, to_commit):
    """Retrieves first and last commit hashes between two points."""
    first_hash = None
    last_hash = None
    commit_obj = None

    if from_commit.hexsha != getattr(to_commit, 'hexsha', None):
        pydriller_repo = pydriller.Repository(
            path,
            from_commit=from_commit.hexsha,
            to_commit=to_commit.hexsha)
    else:
        pydriller_repo = pydriller.Repository(path, single=from_commit.hexsha)

    for commit in pydriller_repo.traverse_commits():
        if first_hash is None:
            first_hash = commit.hash
        last_hash = commit.hash
        commit_obj = commit

    return first_hash, last_hash, commit_obj

def _export_patches(path, patch_dir, first_hash, last_hash, commit_obj):
    """Uses git format-patch to export commits as patches."""
    repo = Repo(path)
    if first_hash == last_hash:
        if commit_obj is not None:
            repo.git.format_patch('-o', patch_dir, commit_obj.hash)
        else:
            exit_with_error("Invalid commit during lookup!")
    else:
        repo.git.format_patch('-o', patch_dir, f"{first_hash}..{last_hash}")

def extract_patches_for_repo(
        path,
        base_dir,
        patchdir,
        baseline_pair,
        include_baseline
        ):
    '''Fetches all patches from a repo between certain baselines'''
    logger.info("Handling baseline pair in: %s", path)
    path = os.path.abspath(path)

    # Find the corresponding 'from' entry for this path
    from_commit = _get_repo_commit(path, baseline_pair["from"])
    if from_commit is None:
        return None

    to_commit = None
    if "to" in baseline_pair:
        to_commit = _get_repo_commit(path, baseline_pair["to"])
        if to_commit is None:
            exit_with_error("Invalid baseline pair configuration!")

    relative_path = os.path.relpath(path, base_dir)
    first_hash, last_hash, commit_obj = _get_commit_hashes(path, from_commit, to_commit)

    patch_dir = os.path.join(patchdir, baseline_pair["name"], relative_path)
    result = data.PatchLayer(
        id=baseline_pair["name"],
        parent=baseline_pair["parent"],
        title=f"Auto-generated layer for baseline: {baseline_pair['name']}",
        description=f"Auto-generated layer for baseline: {baseline_pair['name']}")

    if first_hash and last_hash:
        _export_patches(path, patch_dir, first_hash, last_hash, commit_obj)

        if not include_baseline:
            patch_files = glob.glob(os.path.join(patch_dir, "*.patch"))
            for file in patch_files:
                if is_baseline_patch(os.path.basename(file)):
                    logger.info("Deleting baseline patch: %s", file)
                    os.remove(file)

        # browse the created patches and add them to the patches list
        patch_files = glob.glob(os.path.join(patch_dir, "*.patch"))
        for file in sorted(patch_files):
            result.patches.append(
                data.PatchConfig(
                    basePath=relative_path,
                    patch=os.path.relpath(file, patchdir),
                    updateModulesAfterPatch=False)
                )
    else:
        logger.warning("Missing hashes to export for %s: %s..%s", path, first_hash, last_hash)

    # clean up the created empty patch folders
    remove_empty_folders(patchdir, False)
    if not result:
        exit_with_error("Error extracting patches...")
    return result


def get_baselines(repo):
    '''Returns an directory with the baselines as well as an
    ordered list (newest ... oldest) of the found baselines
    in the given repo as a tupel'''
    baselines = {}
    order = []
    for commit in repo.iter_commits():
        if is_baseline(commit.message):
            key = _get_baseline_name_from_commit(commit)
            if key not in baselines:
                baselines[key] = []
            if key not in order:
                order.append(key)
            baselines[key].append({repo.working_tree_dir: commit})
    return baselines, order


def get_baseline_prefix():
    '''Returns a prefix string defining a baseline commit'''
    return "__tuxLayers_baseline__"


def normalize_workdir_path(workdir):
    '''Checks that we get a string for the workdir argument and removes trailing slashes'''
    if not isinstance(workdir, str):
        exit_with_error("Need to pass string for workdir but reveiced " + str(type(workdir)))
    return workdir.rstrip(os.sep)


def get_baseline_seperator():
    '''Returns the seperator of the different baseine commit components'''
    return " ||| "


def is_baseline(message):
    '''Checks if a given commit message is a correctly-formatted baseline string'''
    parts = get_message_parts(message)
    if not parts or len(parts) != 3:
        return False
    parts[2] = parts[2].strip()  # need to remove the trailing \n that gets added...
    return parts[0] == get_baseline_prefix() and parts[1] == get_hash(parts[2])

def is_baseline_patch(filename):
    '''A simple way of checking if a patchfile is created from a baseline commit'''
    # this _is_ hacky and it _might_ fail if we do weird stuff /w commit naming...
    if not filename.endswith(".patch"):
        return False
    return not filename.startswith(get_baseline_prefix()) and get_baseline_prefix() in filename
    # we might check for the hash but this _should_ be clean enough for now.
    ## TODO: Do this right.


def baselines_are_valid(baselines):
    '''Checks the baseline definition for validity (correct order, non-empty, ...)'''
    # simple but inefficient: we compare the keys of the first entry
    # to the rest of them
    # also len() needs to be the same
    if len(baselines) == 0:
        # by definition: no baselines is valid
        return True
    logger.info("checking baselines")

    first_repo_baselines = list(baselines.values())[0]
    first_length = len(first_repo_baselines)

    for repo, baseline in baselines.items():
        if len(baseline) != first_length:
            logger.warning("Baseline mismatch found for repo %s!", repo)
            logger.warning(pprint.pformat(baseline, indent=2))
            return False
    return True


def get_message_parts(message):
    '''Returns the parts of commit message, split by the baseline operator'''
    return message.split(get_baseline_seperator())


def get_hash(message):
    '''Creates a message hash for use inside a baseline commit'''
    return hashlib.sha512(str(message).encode('utf-8')).hexdigest()


def create_baseline_string(message):
    '''Builds a correct baseline commti string'''
    result = get_baseline_prefix()
    result += get_baseline_seperator()
    result += get_hash(message)
    result += get_baseline_seperator()
    result += message
    return result


def get_baselines_from_path(path, order, quiet):
    '''Extracts the baselines from a given'''
    repo = Repo(path)
    if order == 0:
        baselines, baseline_order = get_baselines(repo)
    else:
        baselines = get_baselines(repo)[0]
        baseline_order = []
    if not quiet:
        logger.info("Showing repo of order %d in %s, %d baselines:",
                    order, repo.working_tree_dir, len(baselines))
        for baseline in baselines:
            logger.info("- %s", baseline)
    for module in repo.submodules:
        module_baselines = get_baselines_from_path(
            module.module().working_tree_dir, order+1, quiet)[0]
        for key, value in module_baselines.items():
            if key not in baselines:
                baselines[key] = []
            baselines[key].extend(value)
    return baselines, baseline_order


def add_recursive_commit(path, commit_msg, add_newly_created_too=False):
    '''Adds a given empty commit to a repository and all its submodules'''
    repo = Repo(os.path.abspath(path))
    for module in repo.submodules:
        add_recursive_commit(module.module().working_tree_dir, commit_msg, add_newly_created_too)
    if add_newly_created_too:
        repo.git.add('-A')
        repo.git.commit('--allow-empty', '-m', commit_msg)
    else:
        repo.git.commit('--allow-empty', '-a', '-m', commit_msg)


def reset_hard_to_baseline(path, baseline):
    ''' Reset the repo at path to the the commit previous to
    the one contained in the baseline object for the given path'''
    repo = Repo(path)
    for module in repo.submodules:
        logger.info(module)
        reset_hard_to_baseline(
            module.module().working_tree_dir, baseline)

    repo_commit = _get_repo_commit(path, baseline)
    if repo_commit is None:
        exit_with_error("Could not find baseline commit in repo " + path)

    logger.info("path: %s", path)
    logger.info(repo_commit)
    logger.info(repo_commit.parents)
    if not repo_commit.parents:
        exit_with_error("Invalid repo configuration: commit " +
                        str(repo_commit) + " has no parents!")
    new_commit = repo_commit.parents[0]
    logger.info("Resetting to %s", new_commit)
    repo.git.reset('--hard', new_commit)


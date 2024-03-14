'''Patchset handles everything regarding reading, applying and documenting patch layers'''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import datetime
import logging
import os
import shutil
import stat
import string
import copy
import sys

import click
import git

import jinja2

from md2pdf.core import md2pdf

from configuration import data
from shared.helpers import exit_with_error, need_layer_config

from commands import baseline

# Logging setup...
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    '--layer', '-l', required=False,
    type=click.STRING,
    help='Selects the layer.')
@click.option(
    '--patchdir', '-p', required=False,
    type=click.Path(),
    default=os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "config", "patches"),
    help='''Target folder that holds patches
    configured in the used configuration. Defaults to config/patches above the executable.''')
@click.option(
    '--all_patchsets', '-a', is_flag=True, required=False,
    type=click.BOOL, default=False, help='If set, all full patchsets are created.')
@click.argument('outpath', type=click.Path())
@click.pass_context
def patchset(ctx, layer, patchdir, outpath, all_patchsets):
    '''Create a patchset for a given layer. If "all" is selected: for each full
    path through the tree (e.g. for each leaf) creates a full patchset.'''
    need_layer_config(ctx)
    if all_patchsets:
        create_all_sets(ctx, patchdir, outpath)
    else:
        if layer:
            _patchset_internal(ctx, layer, patchdir, outpath)
        else:
            exit_with_error("You need to specify either a layer using -l or -a for all layers.")

@click.command()
@click.option(
    '--layer', '-l', required=True,
    type=click.STRING,
    help='Selects the layer.')
@click.option(
    '--patchdir', '-p', required=False,
    type=click.Path(),
    default=os.path.join(os.path.dirname(
        os.path.realpath(sys.modules['__main__'].__file__)),
        "config",
        "patches"),
    help='''Target folder that holds patches
    configured in the used configuration.''')
@click.option(
    '--templatefile', '-t', required=False,
    type=click.Path(),
    default="",
    help='''Create a document displaying all information contained in the layer
            and the patches therein. Defaults to a minimal template.
            Extracting Patch information in this way:
            - each line starting with #
            - until the first occurrence of --- (describing the start of the first patch)
            ''')
@click.option(
    '--misc', '-m', required=False,type=(str, str), multiple=True,
    help='''Allows the user to acc key/value pairs that are available
    during document generation via data.misc.<key>. So calling
    -m my_key 42 will result in typing "42" upon
    referencing {{data.misc.my_key}}'''
)
@click.option(
    '--topdf', is_flag=True, required=False,
    type=click.BOOL, default=False,
    help='''If we use a markdown file / template as an input,
     convert it to pdf after generating it.''')
@click.argument('outpath', type=click.Path(), default=".")
@click.pass_context
def document(ctx, layer, patchdir, templatefile, misc, topdf, outpath):
    '''Create a documentation for a given layer. The -path you
    provide needs to exists and defaults to \".\". The filename
     will be created using the template filename the a timestamp prefix;
     with - if applicable - the .jinja2 suffix removed. If no template was given
    <timestamp>_default.md is used.'''

    need_layer_config(ctx)

    if not os.path.exists(outpath):
        exit_with_error("Outpath must exist: " + outpath)

    logger.info("Creating documentation for layer %s, writing to %s", layer, outpath)
    doc_data = data.Documentation()
    patch_set = create_patchset(ctx, layer)
    for patch in patch_set.patches:
        if not patch.is_patch():
            continue
        patchfile = os.path.join(patchdir, patch.patch)
        logger.info("Comments for file %s", patchfile)
        patch_info = data.PatchInfo()
        patch_info.patchfile = patchfile
        patch_info.patchfile_basename = os.path.basename(patchfile)
        comment = extract_patch_commente(patchfile)
        if comment:
            patch_info.comments = comment
            patch_info.joined_comment = str("\n").join(patch_info.comments)
        doc_data.patches.append(patch_info)


    for entry in misc:
        doc_data.misc[entry[0]] = entry[1]
        logger.info("Misc. key found: %s: %s", entry[0], entry[1])
    logger.info(doc_data.misc)
    if templatefile:
        if not os.path.isfile(templatefile):
            exit_with_error("Template file not found: " + templatefile)
        with open(templatefile, "r", encoding="utf-8") as jinja_template:
            template = jinja_template.read()
    else:
        template = '''# Documentation for layer {{ data.primaryLayer }}

Created on {{data.timestamp}}

# Handled layers:

{% for layer in data.layers -%}
  {{layer.id}}: {{layer.title}}  
{% endfor %}

# Release Overview:

{% for layer in data.layers -%}
  {{layer.description}}  
{% endfor %}

# Patches

A patchset creating the following patches was created from the layer definitions:

{% for patch in data.patches %}
## Patch: {{patch.patchfile_basename}}
{% if patch.comments -%}
{% for commentLine in patch.comments -%}
{{commentLine}}  
{% endfor %}
{% else -%}
*No comment found*
{% endif -%}
{% endfor %}


# THIS IS THE DEFAULT TEMPLATE; PLEASE PROVIDE A CORRECT TEMPLATE FILE INSTEAD

'''

    for referred_layer in get_all_referred_layers(layer, ctx.obj['LAYER_TREE']):
        doc_data.layers.append(
            data.LayerInfo(
                id=referred_layer.id,
                title = referred_layer.title,
                description=referred_layer.description)
            )
    doc_data.primaryLayer = layer
    now = datetime.datetime.utcnow()
    doc_data.timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    #logger.info(template)
    tpl = jinja2.Template(template)
    result = tpl.render(data=doc_data).replace('_', r'\_')
    if templatefile:
        result_filename = now.strftime(
            "%Y%m%d-%H%M%S"
        ) + os.path.basename(templatefile)
        result_filename = result_filename.rstrip(".jinja2")
    else:
        result_filename = now.strftime("%Y%m%d-%H%M%S_default.md")
    logger.info("Writing documenatation to %s in %s", result_filename, outpath)
    with open(os.path.join(outpath, result_filename), 'w', encoding="utf-8") as outfile:
        outfile.write(result)
    if topdf:
        if not result_filename.endswith(".md"):
            exit_with_error('''md2pfd only applicable for .md templates.''')
        pdf_filename = os.path.splitext(result_filename)[0] + ".pdf"
        md2pdf(os.path.join(outpath, pdf_filename),
               md_file_path=os.path.join(outpath, result_filename))

@click.command()
@click.option(
    '--patch_set', '-p', required=False,
    type=click.Path(),
    help='Path that holds a previously created patchset.')
@click.option(
    '--workdir', '-w', required=True,
    type=click.Path(exists=True),
    default='.',
    help='Workdir that holds the repo(s) to apply patches to.')
@click.option(
    '--addBaselines', '-b',
    is_flag=True,
    required=False,
    type=click.BOOL,
    default=False,
    help='If set, baselines found in the patch configuration are added to the target repo.')
@click.option(
    '--fixWhitespace',
    is_flag=True,
    required=False,
    type=click.BOOL,
    default=False,
    help='If set, instead of running "git apply -3", we use "git apply --ignore-space-change --ignore-whitespace --reject')
@click.option(
    '--fromLayer', '-f',
    required=False,
    type=click.STRING,
    default='',
    help='If we are adding baselines, start from this layer.')
def apply(patch_set, workdir, addbaselines, fromlayer, fixwhitespace):
    '''Runs the patchset in the given path in
     the provided workdir'''

    patchset_dir = os.path.abspath(patch_set)

    if not os.path.isdir(patchset_dir):
        exit_with_error("Patch dir invalid")

    if not addbaselines and len(fromlayer) != 0:
        exit_with_error('''Found the 'fromlayer' argument but missing
                        'addBaselines' - did you forget to add this?''')

    patches = load_patches(patch_set)
    logger.info("Loaded patcheset...")

    previous_work_dir = os.path.abspath(os.getcwd())
    work_dir = os.path.abspath(workdir)

    adding_patches = len(fromlayer) == 0
    if not adding_patches:
        logger.info("Looking for layer %s before starting patching!",  fromlayer)
    if not os.path.isdir(work_dir):
        exit_with_error("Patch dir invalid")

    for patch in patches.patches:
        os.chdir(os.path.join(work_dir, patch.basePath))
        if not patch.valid():
            exit_with_error("Invalid patch configuration: " + str(patch))
        if patch.is_baseline():
            logger.info("Found baseline in patch config.")
            # check if we need to activate patching
            if not adding_patches and patch.baseline == fromlayer:
                logger.info("Found start layer! Patching now!")
                adding_patches = True
            if adding_patches:
                baseline.add_baseline_internal(work_dir, patch.baseline)
        elif adding_patches:
            try:
                repo = git.Repo(".")
                patch_file = os.path.join(os.path.abspath(patchset_dir), patch.patch)
                logger.info("Running patch %s!", patch.patch)
                if not fixwhitespace:
                    repo.git.apply(['-3', patch_file])
                else:
                    repo.git.apply(['--ignore-space-change', '--ignore-whitespace', '-3', patch_file])
                repo.git.commit(['-m', "Applied patch " + patch.patch])

            except git.exc.GitError as error:
                os.chdir(previous_work_dir)
                exit_with_error("Git error: " + str(error))

        os.chdir(previous_work_dir)


def get_all_referred_layers(layer, tree):
    ''' Returns a list of all layers between the root and layer'''
    node = tree.get_node(layer)
    if node is None:
        exit_with_error("Unknown layer " + layer + " requested.")

    layers = []
    while node is not None:
        logger.info("Handling layer %s...", node.identifier)
        layers.append(node.data)
        node = tree.parent(node.identifier)
    return reversed(layers)

def create_all_sets(ctx, patchdir, outpath):
    """For each full path through the tree
    (e.g. for each leaf) creates a full patchset"""

    if os.path.exists(outpath):
        exit_with_error("Outpath may not exist: " + outpath)

    tree = ctx.obj['LAYER_TREE']
    for leaf in tree.leaves():
        logger.info("Creating patchset for leaf %s", leaf.identifier)
        _patchset_internal(ctx, leaf.identifier, patchdir,
                           os.path.join(outpath, leaf.identifier))
        logger.info("Done!")
    logger.info("Created %d full patchsets", len(tree.leaves()))


def create_patchset(ctx, layer):
    '''Creates a patchset for the selected layer'''
    tree = ctx.obj['LAYER_TREE']

    layers = get_all_referred_layers(layer, tree)

    patch_set = data.PatchSet()
    # now append all patches in correct order (from selected layer to root)

    current_layer = ''
    for referred_layer in layers:
        if referred_layer.id is not current_layer:
            baseline_patch_entry = data.PatchConfig(
                basePath="",
                patch="",
                baseline=referred_layer.id)
            patch_set.patches.append(baseline_patch_entry)
            current_layer = referred_layer.id
        patch_set.patches.extend(referred_layer.patches)
    logger.info("Created patchset containing %d patches",
                len(patch_set.patches))

    return patch_set

def _patchset_internal(ctx, layer, patchdir, outpath):
    '''Create a patchset for a given layer.'''
    if os.path.exists(outpath):
        exit_with_error("Outpath may not exist: " + outpath)

    patch_set = create_patchset(ctx, layer)
    # write patch info file to our folder...
    logger.info("Creating output folder %s", outpath)
    os.makedirs(outpath)
    # fetch the patches and copy them to the outpath.
    # Rename patches in order and update the patch_set info
    logger.info("Collecting patches...")
    patch_set = collect_patches(patchdir, patch_set, outpath)

    logger.info("Writing patch file...")
    with open(os.path.join(outpath, "patches.json"), "w", encoding="utf-8") as outfile:
        outfile.write(patch_set.to_json(indent=2))

    # write script file to apply the patches independently
    logger.info("Creating runPatches.sh...")

    create_run_patches(patch_set, outpath)


def collect_patches(patchdir, patch_set, target_path):
    """Collects the patch files, renames them in order
    and updates their information in the patch_set.
    Returns a (deep) copy of the patch_set with modified
    filenames."""
    current_index = 1

    if not os.path.exists(patchdir):
        exit_with_error("Patchdir not found: " + patchdir)
    if not os.path.exists(target_path):
        exit_with_error("Target path not found: " + target_path)
    # First, make a deep copy of the patch_set so we dont keep the modified filenames
    patch_set_copy = copy.deepcopy(patch_set)
    for patch in patch_set_copy.patches:
        if patch.is_baseline():
            continue
        patch_path = os.path.dirname(patch.patch)
        patch_filename = os.path.basename(patch.patch)
        os.makedirs(os.path.join(target_path, patch.basePath), exist_ok=True)
        new_filename = os.path.join(patch.basePath, str(
            current_index).zfill(5) + "_" + patch_filename)
        try:
            shutil.copy(
                os.path.join(patchdir, patch_path, patch_filename),
                os.path.join(target_path, new_filename))
        except FileNotFoundError as error:
            exit_with_error(error)
        patch.patch = new_filename
        current_index += 1
    return patch_set_copy


# we need this since we want $ in our resulting file...
class CustomTemplate(string.Template):
    '''Helper class to allow for a specific delimiter for our template'''
    delimiter = '_X_X_X_'


def create_run_patches(patch_set, target_path):
    '''Creates a shell script that runs all patches'''
    filename = "runPatches.sh"
    content = '''
#!/bin/bash
get_abs_filename() {
    # $1 : relative filename
    echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
}
'''
    apply_template = CustomTemplate('''
# Patching _X_X_X_basePath with _X_X_X_patch_file
full_filename=$(get_abs_filename "_X_X_X_patch_file")
_X_X_X_pushd _X_X_X_basePath
git apply $full_filename
git commit -m "Applied patch _X_X_X_patch_file"
_X_X_X_popd''')
    update_template = '''
# Submodule changed, updating...
git submodule update --init --recursive
'''
    for patch in patch_set.patches:
        if patch.is_baseline():
            continue
        logger.info(os.path.basename(patch.patch))
        # comment is a hack to comment out popd/pushd when not changing folders
        config = {
            "basePath": patch.basePath,
            "patch_file": os.path.basename(patch.patch),
            "patch_file_full_path": os.path.abspath(patch.patch),
            "popd": "popd" if patch.basePath else "# Still in base folder...",
            "pushd": "pushd" if patch.basePath else "# Staying in base folder..."}
        content += apply_template.substitute(config)
        if patch.updateModulesAfterPatch:
            content += update_template
        content += "\n"
    with open(os.path.join(target_path, filename), "w", encoding="utf-8") as outfile:
        outfile.write(content)
    os.chmod(outfile.name, os.stat(outfile.name).st_mode | stat.S_IEXEC)


def load_patches(_patchset):
    '''Loads patches from a patchset file'''
    patches_file = os.path.join(os.path.abspath(
        os.path.join(_patchset)), "patches.json")
    if not os.path.isfile(patches_file):
        exit_with_error("Could not find " + patches_file)
        return {}

    with open(patches_file, encoding='utf-8') as json_content:
        # Further file processing goes here
        data_json = json_content.read()
        try:
            # pylint: disable=no-member
            data_layer = data.PatchSet.from_json(data_json)
            return data_layer
        except ValueError as value_error:
            exit_with_error(value_error)
            return {}


def extract_patch_commente(patchfile):
    '''Extract a comment to a patch greedily by first looking
     for # at the start of each line until we find --- (the start of the patch.)'''
    patch_delimiter='---'
    comment_delimiter='#'
    comments = []
    with open(patchfile, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line.startswith(patch_delimiter):
                break
            if line.startswith(comment_delimiter):
                comments.append(line.lstrip(comment_delimiter).strip())
    return comments
